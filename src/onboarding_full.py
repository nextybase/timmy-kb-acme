#!/usr/bin/env python3
# src/onboarding_full.py
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    PreviewError,
    EXIT_CODES,
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
from pipeline.env_utils import is_log_redaction_enabled  # 👈 toggle centralizzato


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


def onboarding_full_main(
    slug: str,
    *,
    non_interactive: bool = False,
    dry_run: bool = False,
    no_drive: bool = False,
    push: Optional[bool] = None,
    port: int = 4000,
) -> None:
    require_env = not (no_drive or dry_run or non_interactive)
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=require_env,
    )
    log_file = Path("output") / f"timmy-kb-{slug}" / "logs" / "onboarding.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context)

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
    redact = is_log_redaction_enabled(context)

    # Controllo precoce Docker / policy preview
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
                while True:
                    ans = _confirm_yes_no("Hai attivato Docker? Vuoi riprovare ora il controllo?", default_no=False)
                    if not ans:
                        raise ConfigError("Anteprima richiesta ma Docker non è stato attivato. Interruzione.")
                    if _docker_available():
                        logger.info("✅ Docker rilevato. La preview sarà attivata più avanti.")
                        preview_allowed = True
                        break
                    else:
                        logger.warning("⚠️  Docker ancora non disponibile. Puoi riprovare o annullare.")

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
            redact_logs=redact,  # 🔐 redazione log secondo policy
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

    # 3) Preview HonKit in Docker (mai bloccante)
    container_name = f"honkit_preview_{slug}"
    preview_started = False
    if preview_allowed and _docker_available():
        logger.info("🔎 Docker disponibile: avvio preview HonKit (detached)")
        run_gitbook_docker_preview(
            context,
            port=port,
            container_name=container_name,
            wait_on_exit=False,
            redact_logs=redact,  # 🔐 passa il toggle anche alla preview
        )
        preview_started = True
        logger.info(f"▶️ Anteprima su http://localhost:{port} (container: {container_name})")
    elif preview_allowed:
        logger.warning("⚠️ Docker non più disponibile al momento dell'avvio: anteprima saltata")
    else:
        logger.info("⏭️  Anteprima disabilitata per scelta/policy iniziale")

    # 4) Push su GitHub (opzionale) — cleanup del container in finally, SEMPRE
    token = context.env.get("GITHUB_TOKEN")
    if push is not None:
        do_push = push
    else:
        do_push = False if non_interactive else _confirm_yes_no("Eseguire il push su GitHub?", default_no=True)

    try:
        if do_push:
            if not token:
                raise ConfigError("GITHUB_TOKEN mancante: impossibile eseguire il push.")

            logger.info("📤 Avvio push su GitHub")
            push_output_to_github(context, github_token=token, do_push=True, redact_logs=redact)

            # ➕ Prompt pulizia artefatti push (solo interattivo)
            if not non_interactive and _confirm_yes_no(
                "Pulire eventuali artefatti locali di push legacy (es. .git in book/)?",
                default_no=True,
            ):
                try:
                    report = clean_push_leftovers(context)
                    logger.info("🧹 Cleanup artefatti completato", extra=report)
                except Exception as e:
                    logger.warning("⚠️  Cleanup artefatti fallito", extra={"error": str(e)})
        else:
            logger.info("⏭️  Push su GitHub non eseguito")
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
    p.add_argument("--push", action="store_true", help="Forza il push su GitHub (solo se GITHUB_TOKEN è presente)")
    p.add_argument("--no-push", action="store_true", help="Disabilita esplicitamente il push su GitHub")
    p.add_argument("--skip-drive", action="store_true", help="(Deprecato) Usa --no-drive")
    p.add_argument("--skip-push", action="store_true", help="(Deprecato) Usa --no-push")
    p.add_argument("--port", type=int, default=4000, help="Porta locale per la preview HonKit (default: 4000)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    early_logger = get_structured_logger("onboarding_full")

    slug = args.slug_pos or args.slug
    if not slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    if not slug:
        slug = _prompt("Inserisci slug cliente: ").strip()

    if args.skip_drive:
        early_logger.warning("⚠️  --skip-drive è deprecato; usare --no-drive")
        args.no_drive = True
    if args.skip_push:
        early_logger.warning("⚠️  --skip-push è deprecato; usare --no-push")
        args.no_push = True

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
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except PipelineError as e:
        code = EXIT_CODES.get(e.__class__.__name__, EXIT_CODES.get("PipelineError", 1))
        sys.exit(code)
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    except PreviewError:
        sys.exit(EXIT_CODES.get("PreviewError", 30))
    except Exception:
        sys.exit(EXIT_CODES.get("PipelineError", 1))
