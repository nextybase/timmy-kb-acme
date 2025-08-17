#!/usr/bin/env python3
# src/onboarding_full.py
"""Orchestratore della fase di **onboarding completo** per Timmy-KB.

Responsabilità (immutate):
- Orchestrare il flusso end-to-end: download PDF (opzionale), conversione in Markdown,
  generazione `SUMMARY.md`/`README.md`, preview HonKit in Docker (se disponibile) e push (opzionale).
- Gestire UX/CLI (prompt, conferme) e il mapping deterministico **eccezioni → EXIT_CODES**.
- Delegare il lavoro tecnico ai moduli di `pipeline.*` (i moduli **non** terminano il processo
  e **non** chiedono input).

Comportamento UX:
- **non_interactive=True** → nessun prompt; se Docker non c’è la preview è **saltata**; `push=False`
  salvo override `--push`.  
- **non_interactive=False** → prompt sulla preview quando Docker manca; prompt sul push (default no).

Sicurezza/Log:
- Logger **condiviso** per cliente (file unico), niente segreti in chiaro; coerenza con policy dei log.
"""

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


# -----------------------
# Helpers interazione CLI
# -----------------------
def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato **solo** negli orchestratori).

    Args:
        msg: Messaggio da mostrare all’utente.

    Returns:
        La risposta inserita dall’utente (ripulita con `strip()`).

    Note:
        I moduli di `pipeline.*` non devono usare prompt.
    """
    return input(msg).strip()


def _confirm_yes_no(msg: str, default_no: bool = True) -> bool:
    """Chiede conferma sì/no con default configurabile.

    Args:
        msg: Testo della domanda (senza suffisso).
        default_no: Se `True`, default = **No** (`[y/N]`), altrimenti **Sì** (`[Y/n]`).

    Returns:
        `True` se l’utente conferma (y/yes/s/sì), altrimenti `False`.
    """
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    ans = input(msg + suffix).strip().lower()
    if not ans:
        return not default_no
    return ans in ("y", "yes", "s", "si", "sí")


def _docker_available() -> bool:
    """Verifica la disponibilità del comando `docker` nel PATH.

    Returns:
        `True` se `docker --version` esegue con successo, altrimenti `False`.

    Notes:
        In **non-interattivo** la preview viene **saltata** se Docker non è disponibile.
    """
    try:
        # Controllo semplice: esistenza comando docker
        subprocess.run(["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


# -----------------------------------
# Orchestratore principale (flusso)
# -----------------------------------
def onboarding_full_main(
    slug: str,
    *,
    non_interactive: bool = False,
    dry_run: bool = False,
    no_drive: bool = False,
    push: Optional[bool] = None,
    port: int = 4000,
) -> None:
    """Esegue l'onboarding completo per il cliente indicato da `slug`.

    Fasi:
      1) (opz.) Download PDF da Drive → `output/<slug>/raw/`
      2) Conversione/Generazione Markdown → `output/<slug>/book/`
      3) (opz.) Preview HonKit in Docker
      4) (opz.) Push su GitHub

    UX invariata:
      - `non_interactive=True`: nessun prompt; se Docker non c'è → **skip preview**; `push=False` salvo `--push`.
      - `non_interactive=False`: prompt su preview se Docker manca; prompt su push (default **no**).

    Args:
        slug: Identificativo cliente (usato per risolvere la root `output/timmy-kb-<slug>`).
        non_interactive: Se `True`, esecuzione batch senza prompt.
        dry_run: Se `True`, nessun accesso ai servizi remoti (Drive); esegue solo la parte locale.
        no_drive: Se `True`, salta il download da Drive anche quando non è dry-run.
        push: `True` forza il push; `False` lo disabilita; `None` → decide UX (prompt o default).
        port: Porta locale per la preview HonKit (default: 4000).

    Raises:
        ConfigError: Config mancante/errata (es. `drive_raw_folder_id` assente) o richieste UX non soddisfatte.
        PreviewError: Errori legati all’anteprima HonKit (propagati dai moduli).
        PipelineError: Errori non tipizzati propagati dai moduli.

    Side Effects:
        - Scrive markdown e file di log sotto `output/timmy-kb-<slug>/`.
        - Può creare/leggere risorse su Google Drive e avviare un container Docker per la preview.
        - Può effettuare un push su GitHub (se autorizzato).
    """
    # Carica contesto e logger file-based unificato
    context: ClientContext = ClientContext.load(slug=slug, interactive=not non_interactive)
    log_file = Path("output") / f"timmy-kb-{slug}" / "logs" / "onboarding.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context)

    logger.info("🚀 Avvio onboarding_full")

    # Config cliente
    try:
        cfg: Dict[str, Any] = get_client_config(context) or {}
    except ConfigError as e:
        logger.error(str(e))
        raise

    # 1) Download da Drive (opzionale)
    if not no_drive and not dry_run:
        drive_raw_folder_id = cfg.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError(
                "ID cartella RAW su Drive mancante in config.yaml (chiave: drive_raw_folder_id)."
            )
        logger.info(f"📥 Download PDF da Drive (RAW={drive_raw_folder_id}) → {context.raw_dir}")
        service = get_drive_service(context)
        download_drive_pdfs_to_local(
            service=service,
            remote_root_folder_id=drive_raw_folder_id,
            local_root_dir=context.raw_dir,
            progress=not non_interactive,
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

    # 3) Preview HonKit in Docker (se possibile/consentita)
    if _docker_available():
        logger.info("🔎 Docker disponibile: avvio preview HonKit")
        run_gitbook_docker_preview(
            context,
            port=port,
            container_name=f"honkit_preview_{slug}",
            wait_on_exit=not non_interactive,
        )
    else:
        logger.warning("⚠️ Docker non disponibile")
        if non_interactive:
            logger.info("⏭️  Modalità non-interattiva: anteprima saltata automaticamente")
        else:
            proceed = _confirm_yes_no("Docker non disponibile. Vuoi continuare senza anteprima?", default_no=True)
            if not proceed:
                raise ConfigError("Anteprima richiesta ma Docker non disponibile (interruzione su richiesta).")
            logger.info("⏭️  Anteprima saltata su scelta dell'utente")

    # 4) Push su GitHub (opzionale)
    token = context.env.get("GITHUB_TOKEN")
    do_push: bool
    if push is not None:
        do_push = push
    else:
        do_push = False if non_interactive else _confirm_yes_no("Eseguire il push su GitHub?", default_no=True)

    if do_push:
        if not token:
            raise ConfigError("GITHUB_TOKEN mancante: impossibile eseguire il push.")
        logger.info("📤 Avvio push su GitHub")
        push_output_to_github(context, github_token=token, confirm_push=True)
    else:
        logger.info("⏭️  Push su GitHub non eseguito")

    logger.info("✅ Onboarding completo")


# -----------------------
# Argparse / __main__
# -----------------------
def _parse_args() -> argparse.Namespace:
    """Parsa gli argomenti CLI dell’orchestratore `onboarding_full`.

    Returns:
        Namespace con:
            - `slug_pos`: slug posizionale (opzionale).
            - `--slug`: slug esplicito (retrocompat).
            - `--non-interactive`: esecuzione senza prompt.
            - `--dry-run`: nessun accesso ai servizi remoti; conversione locale.
            - `--no-drive`: forza lo skip del download da Drive.
            - `--push` / `--no-push`: controlla il push su GitHub (alias deprecati supportati).
            - `--port`: porta locale per la preview HonKit.
    """
    p = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")

    # Slug “soft” posizionale con compat --slug
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")

    # Modalità/controllo flusso
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--dry-run", action="store_true", help="Nessun accesso a servizi remoti; esegue conversione locale")
    p.add_argument("--no-drive", action="store_true", help="Salta sempre download da Drive")

    # Push
    p.add_argument("--push", action="store_true", help="Forza il push su GitHub (solo se GITHUB_TOKEN è presente)")
    p.add_argument("--no-push", action="store_true", help="Disabilita esplicitamente il push su GitHub")

    # Alias storici (deprecati)
    p.add_argument("--skip-drive", action="store_true", help="(Deprecato) Usa --no-drive")
    p.add_argument("--skip-push", action="store_true", help="(Deprecato) Usa --no-push")

    # Preview
    p.add_argument("--port", type=int, default=4000, help="Porta locale per la preview HonKit (default: 4000)")

    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # Logger console “early” (prima di avere lo slug) per messaggi iniziali
    early_logger = get_structured_logger("onboarding_full")

    # Risoluzione slug
    slug = args.slug_pos or args.slug
    if not slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    if not slug:
        slug = _prompt("Inserisci slug cliente: ").strip()

    # Normalizza alias deprecati
    if args.skip_drive:
        early_logger.warning("⚠️  --skip-drive è deprecato; usare --no-drive")
        args.no_drive = True
    if args.skip_push:  # <-- manteniamo l'alias deprecato con warning
        early_logger.warning("⚠️  --skip-push è deprecato; usare --no-push")
        args.no_push = True

    # Determinazione push (priorità: --no-push > --push)
    push_flag: Optional[bool]
    if args.no_push:
        push_flag = False
    elif args.push:
        push_flag = True
    else:
        push_flag = None  # domanda in interattivo, false in non-interattivo

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
