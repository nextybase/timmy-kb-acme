#!/usr/bin/env python3
# src/onboarding_full.py
from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    PreviewError,
    EXIT_CODES,
    ForcePushError,  # ✅ usa l'eccezione specifica per il gate force
)
from pipeline.context import ClientContext
from pipeline.config_utils import get_client_config
from pipeline.drive_utils import (
    get_drive_service,
    download_drive_pdfs_to_local,
)
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
    validate_markdown_dir,
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup_utils import clean_push_leftovers  # ➕ cleanup post-push
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME, LOG_FILE_NAME
from pipeline.path_utils import validate_slug as _validate_slug_helper
from pipeline.exceptions import InvalidSlug  # eccezione dominio per slug non valido
from pipeline.env_utils import (  # ✅ allow-list branch + lettura env
    is_branch_allowed_for_force,
    get_env_var,
)


def _prompt(msg: str) -> str:
    return input(msg).strip()


def _confirm_yes_no(msg: str, default_no: bool = True) -> bool:
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    ans = input(msg + suffix).strip().lower()
    if not ans:
        return not default_no
    return ans in ("y", "yes", "s", "si", "sí")


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def _stop_preview_container(container_name: str) -> None:
    subprocess.run(["docker", "rm", "-f", container_name], check=False)


def _ensure_valid_slug(initial_slug: Optional[str], interactive: bool, early_logger) -> str:
    """Valida/ottiene uno slug valido PRIMA di creare contesto/logger file-based."""
    slug = (initial_slug or "").strip()
    while True:
        if not slug:
            if not interactive:
                raise ConfigError("Slug mancante.")
            slug = _prompt("Inserisci slug cliente: ").strip()
            continue
        try:
            _validate_slug_helper(slug)  # alza InvalidSlug se non conforme
            return slug
        except InvalidSlug:
            early_logger.error("Slug non valido secondo le regole configurate. Riprovare.")
            if not interactive:
                raise ConfigError(f"Slug '{slug}' non valido.")
            slug = _prompt("Inserisci uno slug valido (es. acme-srl): ").strip()


# =========================
#   HELPER ESTRATTI (Fase A)
# =========================

def _run_preview(
    context: ClientContext,
    *,
    slug: str,
    port: int,
    docker_retries: int,
    non_interactive: bool,
    redact: bool,
    logger,
) -> bool:
    """Incapsula la logica della preview (check Docker + avvio container)."""
    # Controllo/policy Docker
    preview_allowed = True
    if non_interactive:
        if not _docker_available():
            preview_allowed = False
            logger.info("⏭️  Modalità non-interattiva: Docker assente → anteprima saltata automaticamente")
    else:
        if not _docker_available():
            logger.warning("⚠️ Docker non disponibile")
            if _confirm_yes_no("Vuoi proseguire senza anteprima?", default_no=False):
                preview_allowed = False
                logger.info("⏭️  L'utente ha scelto di proseguire senza anteprima (sarà totalmente esclusa)")
            else:
                logger.info("🛠️  Attiva Docker quindi conferma per riprovare il controllo")
                attempts = 0
                max_attempts = max(1, int(docker_retries))
                while attempts < max_attempts:
                    ans = _confirm_yes_no("Hai attivato Docker? Vuoi riprovare ora il controllo?", default_no=False)
                    if not ans:
                        raise ConfigError("Anteprima richiesta ma Docker non è stato attivato. Interruzione.")
                    if _docker_available():
                        logger.info("✅ Docker rilevato. La preview sarà attivata più avanti.")
                        preview_allowed = True
                        break
                    else:
                        attempts += 1
                        logger.warning(f"⚠️  Docker ancora non disponibile (tentativo {attempts}/{max_attempts}).")
                if attempts >= max_attempts and not preview_allowed:
                    raise ConfigError("Docker non disponibile dopo i tentativi concessi.")

    container_name = f"honkit_preview_{slug}"
    if preview_allowed and _docker_available():
        logger.info("🔎 Docker disponibile: avvio preview HonKit (detached)")
        run_gitbook_docker_preview(
            context,
            port=port,
            container_name=container_name,
            wait_on_exit=False,
            redact_logs=redact,  # 🔐 passa il toggle anche alla preview
        )
        logger.info(f"▶️ Anteprima su http://localhost:{port} (container: {container_name})")
        return True
    elif preview_allowed:
        logger.warning("⚠️ Docker non più disponibile al momento dell'avvio: anteprima saltata")
    else:
        logger.info("⏭️  Anteprima disabilitata per scelta/policy iniziale")
    return False


def _resolve_target_branch(context: ClientContext) -> str:
    """
    Risolve il branch di lavoro coerentemente con il modulo GitHub:
    1) context.env[GIT_DEFAULT_BRANCH] o context.env[GITHUB_BRANCH]
    2) variabili di processo (get_env_var)
    3) fallback 'main'
    """
    if getattr(context, "env", None):
        br = context.env.get("GIT_DEFAULT_BRANCH") or context.env.get("GITHUB_BRANCH")
        if br:
            return str(br)
    br = get_env_var("GIT_DEFAULT_BRANCH") or get_env_var("GITHUB_BRANCH")
    return br or "main"


def _maybe_push(
    context: ClientContext,
    *,
    push_flag: Optional[bool],
    non_interactive: bool,
    redact: bool,
    logger,
    # ✅ Nuovi parametri per governance force push (non I/O nei moduli)
    force_push: Optional[bool] = None,
    force_ack: Optional[str] = None,
) -> None:
    """Incapsula la logica del push (con conferma in interattivo) e cleanup opzionale).

    Policy R1 (governance force push, orchestratore):
    - Non-interactive/CI: force consentito SOLO con entrambi i fattori presenti
      (--force-push + --force-ack <TAG>) → altrimenti ForcePushError (exit 41).
    - Interattivo: se force senza ack, chiedi conferma e acquisisci ack.
    - Allow-list branch: se il branch non è ammesso per il force → ForcePushError.
    """
    token = context.env.get("GITHUB_TOKEN")
    target_branch = _resolve_target_branch(context)

    # Determina se si vuole forzare
    want_force = bool(force_push)

    # Gate force push
    if want_force:
        # allow-list branch
        if not is_branch_allowed_for_force(target_branch, context=context, allow_if_unset=True):
            raise ForcePushError(
                f"Force push non consentito sul branch '{target_branch}' secondo GIT_FORCE_ALLOWED_BRANCHES.",
                slug=context.slug,
            )

        if non_interactive:
            # In CI il force richiede SEMPRE entrambi i fattori
            if not force_ack:
                raise ForcePushError(
                    "Force push in modalità non-interattiva senza --force-ack <TAG>.",
                    slug=context.slug,
                )
            # ok: procederemo passando i flag al modulo GitHub
        else:
            # Interattivo: se manca l'ack, chiedi un tag esplicito
            if not force_ack:
                logger.warning("⚠️ Richiesta di force push senza ACK esplicito.")
                if not _confirm_yes_no("Confermi di voler procedere con un force push?", default_no=True):
                    logger.info("⏭️  Force push annullato dall'utente")
                    want_force = False  # ricade su push normale (se abilitato)
                else:
                    entered = _prompt("Inserisci un tag di conferma (Force-Ack): ").strip()
                    if not entered:
                        raise ForcePushError("Force push annullato: ACK mancante.", slug=context.slug)
                    force_ack = entered  # ✅ acquisito interattivamente

    # Risoluzione intenzione push (normale/incrementale)
    if push_flag is not None:
        do_push = push_flag
    else:
        do_push = False if non_interactive else _confirm_yes_no("Eseguire il push su GitHub?", default_no=True)

    if not do_push:
        logger.info("⏭️  Push su GitHub non eseguito")
        return

    if not token:
        raise ConfigError("GITHUB_TOKEN mancante: impossibile eseguire il push.")

    logger.info(
        "📤 Avvio push su GitHub (%s)",
        "force-with-lease" if want_force else "incrementale",
        extra={"branch": target_branch},
    )

    # ✅ Chiama il modulo GitHub passando i nuovi parametri (force governato)
    push_output_to_github(
        context,
        github_token=token,
        do_push=True,
        force_push=want_force,
        force_ack=force_ack,
        redact_logs=redact,
    )

    # Cleanup artefatti locali post-push (solo interattivo, non bloccante)
    if not non_interactive and _confirm_yes_no(
        "Pulire eventuali artefatti locali di push legacy (es. .git in book/)?",
        default_no=True,
    ):
        try:
            report = clean_push_leftovers(context)
            logger.info("🧹 Cleanup artefatti completato", extra=report)
        except Exception as e:
            # warning intenzionale: non vogliamo far fallire l'onboarding per cleanup
            logger.warning("⚠️  Cleanup artefatti fallito", extra={"error": str(e)})


# =========================
#   FUNZIONE PRINCIPALE
# =========================

def onboarding_full_main(
    slug: str,
    *,
    non_interactive: bool = False,
    dry_run: bool = False,
    no_drive: bool = False,
    push: Optional[bool] = None,
    port: int = 4000,
    allow_offline_env: bool = False,
    docker_retries: int = 3,
    run_id: Optional[str] = None,
    # ✅ Nuovi parametri propagati all’helper push
    force_push: Optional[bool] = None,
    force_ack: Optional[str] = None,
) -> None:
    # Logger console “early” per validazione slug (prima del contesto)
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)

    # ✅ VALIDAZIONE SLUG NELL’ORCHESTRATORE (loop solo qui)
    slug = _ensure_valid_slug(slug, not non_interactive, early_logger)

    # ✅ VALIDAZIONE PORTA: range obbligatorio 1..65535
    if not (1 <= int(port) <= 65535):
        raise ConfigError(f"Porta fuori range: {port}. Valori validi 1..65535.")

    # 🚦 Policy env: se NON è dry-run e NON c'è --no-drive ⇒ require_env=True
    # Override possibile con --allow-offline-env
    if allow_offline_env:
        require_env = not (no_drive or dry_run or non_interactive)
    else:
        require_env = (not no_drive) and (not dry_run)

    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,  # prompt solo negli orchestratori
        require_env=require_env,
        run_id=run_id,
    )

    # 🌟 Logger file-based allineato alle costanti
    log_file = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / LOGS_DIR_NAME / LOG_FILE_NAME
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context, run_id=run_id)

    if not require_env:
        logger.info("🌐 Modalità offline: variabili d'ambiente esterne non richieste (require_env=False).")

    logger.info("🚀 Avvio onboarding_full")

    # Config cliente
    try:
        cfg: Dict[str, Any] = get_client_config(context) or {}
    except ConfigError as e:
        logger.error(str(e))
        raise

    # Toggle redazione centralizzato
    redact = context.redact_logs

    # 1) Download da Drive (opzionale)
    if not no_drive and not dry_run:
        drive_raw_folder_id = cfg.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("ID cartella RAW su Drive mancante in config.yaml (chiave: drive_raw_folder_id).")
        logger.info(f"📥 Download PDF da Drive (RAW={drive_raw_folder_id}) → {context.raw_dir}")
        service = get_drive_service(context)
        download_drive_pdfs_to_local(
            service=service,
            remote_root_folder_id=drive_raw_folder_id,
            local_root_dir=context.raw_dir,
            progress=not non_interactive,
            context=context,
            redact_logs=redact,
        )
    else:
        if no_drive:
            logger.info("⏭️  Skip download da Drive (flag --no-drive)")
        if dry_run:
            logger.info("🧪 Dry-run attivo: nessun accesso a Google Drive")

    # 2) Conversione/generazione Markdown
    logger.info("🧩 Conversione PDF → Markdown strutturato")
    convert_files_to_structured_markdown(context)
    logger.info("🧭 Generazione SUMMARY.md")
    generate_summary_markdown(context)
    logger.info("📘 Generazione README.md")
    generate_readme_markdown(context)
    validate_markdown_dir(context)

    # 3) Preview HonKit in Docker (mai bloccante) — ora incapsulata
    preview_started = False
    container_name = f"honkit_preview_{slug}"
    try:
        preview_started = _run_preview(
            context,
            slug=slug,
            port=port,
            docker_retries=docker_retries,
            non_interactive=non_interactive,
            redact=redact,
            logger=logger,
        )

        # 4) Push su GitHub (opzionale) — incapsulato
        _maybe_push(
            context,
            push_flag=push,
            non_interactive=non_interactive,
            redact=redact,
            logger=logger,
            force_push=force_push,
            force_ack=force_ack,
        )
    finally:
        if preview_started:
            _stop_preview_container(container_name)
            logger.info("🧹 Anteprima fermata automaticamente", extra={"file_path": container_name})

    logger.info("✅ Onboarding completo")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--dry-run", action="store_true", help="Nessun accesso a servizi remoti; esegue conversione locale")
    p.add_argument("--no-drive", action="store_true", help="Salta sempre download da Drive")

    # Push: rendiamo i due flag mutuamente esclusivi per evitare ambiguità
    grp_push = p.add_mutually_exclusive_group()
    grp_push.add_argument("--push", action="store_true", help="Forza il push su GitHub (se GITHUB_TOKEN è presente)")
    grp_push.add_argument("--no-push", action="store_true", help="Disabilita esplicitamente il push su GitHub")

    # ✅ Nuovi flag per governance force-push (gated)
    p.add_argument(
        "--force-push",
        action="store_true",
        help="(Avanzato) Richiedi force push. Richiede anche --force-ack <TAG>.",
    )
    p.add_argument(
        "--force-ack",
        type=str,
        help="Tag di conferma obbligatorio quando si usa --force-push (ack a due fattori).",
    )

    p.add_argument("--port", type=int, default=4000, help="Porta locale per la preview HonKit (default: 4000)")
    p.add_argument(
        "--allow-offline-env",
        action="store_true",
        help="Permette require_env=False anche in modalità non-interactive (uso avanzato/CI).",
    )
    p.add_argument(
        "--docker-retries",
        type=int,
        default=3,
        help="Numero massimo di retry per il controllo Docker in modalità interattiva (default: 3).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    try:
        slug = _ensure_valid_slug(unresolved_slug, not args.non_interactive, early_logger)
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    # Risoluzione del comportamento push
    if args.no_push:
        push_flag = False
    elif args.push:
        push_flag = True
    else:
        push_flag = None

    try:
        onboarding_full_main(
            slug=slug,
            non_interactive=args.non_interactive,
            dry_run=args.dry_run,
            no_drive=args.no_drive,
            push=push_flag,
            port=args.port,
            allow_offline_env=args.allow_offline_env,
            docker_retries=args.docker_retries,
            run_id=run_id,
            # ✅ Propagazione nuovi flag
            force_push=args.force_push,
            force_ack=args.force_ack,
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    # 👇 Ordine corretto: specifiche prima di PipelineError
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    except PreviewError:
        sys.exit(EXIT_CODES.get("PreviewError", 30))
    except PipelineError as e:
        code = EXIT_CODES.get(e.__class__.__name__, EXIT_CODES.get("PipelineError", 1))
        sys.exit(code)
    except Exception:
        sys.exit(EXIT_CODES.get("PipelineError", 1))
