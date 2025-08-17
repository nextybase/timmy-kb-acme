# src/onboarding_full.py
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, ConfigError
from pipeline.context import ClientContext
from pipeline.config_utils import get_client_config
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.github_utils import push_output_to_github
from pipeline.gitbook_preview import (
    ensure_book_json,
    ensure_package_json,
    run_gitbook_docker_preview,
)
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)


def _prompt(msg: str) -> str:
    return input(msg).strip()


def _docker_available(logger) -> bool:
    """
    True se Docker è disponibile e attivo.
    Warning sintetico: non stampa stderr del demone.
    """
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            logger.info("🐳 Docker rilevato e attivo")
            return True
        logger.warning(f"Docker non disponibile (rc={proc.returncode})")
        return False
    except FileNotFoundError:
        logger.warning("Docker non trovato nel PATH")
        return False
    except Exception as e:
        logger.warning(f"Impossibile verificare Docker: {e}")
        return False


def onboarding_full_main(
    slug: str,
    *,
    dry_run: bool = False,
    no_drive: bool = False,
    interactive_mode: bool = True,
    pre_skip_preview: Optional[bool] = None,   # scelta fatta prima dello slug (None=default behavior)
    force_skip_push: bool = False,             # compat: salta push senza prompt
) -> None:
    """
    Onboarding completo per <slug>:
      1) Validazione config
      2) (opz.) Download PDF da Drive → output/<slug>/raw/
      3) Conversione PDF→Markdown → output/<slug>/book/*.md
      4) Generazione SUMMARY.md e README.md
      5) Preview Honkit (Docker)
      6) (opz.) Push su GitHub
    """
    # Logger su file cliente
    log_file = Path("output") / f"timmy-kb-{slug}" / "logs" / "onboarding.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("onboarding_full", log_file=log_file)

    try:
        # Carica contesto
        context: ClientContext = ClientContext.load(slug=slug, interactive=interactive_mode)
        logger.info(f"Config cliente caricata: {context.config_path}")
        logger.info("🚀 Avvio onboarding completo")

        # 1) Validazione config
        logger.info("📑 Validazione configurazione cliente...")
        cfg = get_client_config(context) or {}
        if not dry_run and not no_drive:
            if not cfg.get("drive_raw_folder_id"):
                raise ConfigError("Config mancante di 'drive_raw_folder_id' (pre_onboarding non completato?)")
        logger.info("✅ Configurazione cliente valida")

        # 2) Download PDF da Drive
        if not dry_run and not no_drive:
            logger.info("📥 Avvio download PDF da Google Drive...")
            service = get_drive_service(context)
            raw_root_id = cfg["drive_raw_folder_id"]
            download_drive_pdfs_to_local(
                service=service,
                remote_root_folder_id=raw_root_id,
                local_root_dir=Path(context.raw_dir),
                progress=True,
            )
            logger.info("✅ Download PDF completato")
        else:
            logger.info("⏭️  Download da Drive saltato (dry-run o no-drive)")

        # 3) Conversione PDF → Markdown
        logger.info("📄 Avvio conversione PDF in Markdown...")
        convert_files_to_structured_markdown(context)
        logger.info("✅ Conversione completata")

        # 4) SUMMARY.md + README.md
        logger.info("📝 Generazione SUMMARY.md e README.md...")
        generate_summary_markdown(context)
        generate_readme_markdown(context)
        logger.info("✅ SUMMARY.md e README.md generati")

        # 5) Preview Honkit (Docker) — rispetta il pre-check
        skip_preview = False
        if pre_skip_preview is True:
            skip_preview = True
            logger.info("⏭️  Anteprima GitBook saltata (scelta utente al pre-check Docker)")
        elif pre_skip_preview is False:
            if not _docker_available(logger):
                raise ConfigError("Anteprima richiesta ma Docker non è disponibile. Avvia Docker e riprova.")
        else:
            docker_ok = _docker_available(logger)
            if not docker_ok:
                if interactive_mode:
                    ans = _prompt("⚠️  Docker non è attivo. Proseguire senza anteprima? (y/n): ").lower()
                    if ans.startswith("y"):
                        skip_preview = True
                        logger.info("⏭️  Anteprima GitBook saltata per scelta utente")
                    else:
                        raise ConfigError("Anteprima richiesta ma Docker non è disponibile. Avvia Docker e riprova.")
                else:
                    logger.info("⏭️  Anteprima GitBook saltata (non-interactive e Docker non disponibile)")
                    skip_preview = True

        if not skip_preview:
            logger.info("🌐 Avvio anteprima GitBook...")
            ensure_book_json(book_dir=Path(context.md_dir), slug=context.slug)
            ensure_package_json(book_dir=Path(context.md_dir), slug=context.slug)
            run_gitbook_docker_preview(
                context=context,
                port=4000,
                container_name="honkit_preview",
                wait_on_exit=True,
            )
            logger.info("✅ Anteprima GitBook completata")

        # 6) Push GitHub (opzionale)
        logger.info("📤 Avvio push su GitHub...")
        if force_skip_push:
            logger.info("⏭️  Push GitHub saltato (flag)")
        else:
            do_push = False
            if interactive_mode:
                ans = _prompt("Vuoi eseguire il push su GitHub? (y/n): ").lower()
                do_push = ans.startswith("y")
            if do_push:
                token = context.env.get("GITHUB_TOKEN")
                if not token:
                    raise ConfigError("GITHUB_TOKEN non configurato nell'ambiente (.env).")
                push_output_to_github(context, github_token=token, confirm_push=True)
                logger.info("✅ Push GitHub completato")
            else:
                logger.info("⏭️  Push GitHub non eseguito")

        logger.info("🎯 Onboarding completato con successo")

    except (PipelineError, ConfigError) as e:
        logger.error(str(e), exc_info=True)
        raise
    except KeyboardInterrupt:
        logger.warning("Operazione annullata dall'utente.")
        raise
    except Exception as e:
        logger.error(f"Errore imprevisto: {e}", exc_info=True)
        raise


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Onboarding completo NeXT KB")
    # Posizionale FACOLTATIVO + alias opzionale --slug
    p.add_argument("slug", nargs="?", help="Slug cliente (es. acme-srl)")
    p.add_argument("--slug", dest="slug_kw", help="Slug cliente (alternativa posizionale)")
    # Flag moderni
    p.add_argument("--dry-run", action="store_true", help="Salta Drive e GitHub; esegue solo conversione/preview")
    p.add_argument("--no-drive", action="store_true", help="Non scarica da Drive (usa PDF già presenti in raw/)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt (skip push)")
    # Compat con flag storici (mappati)
    p.add_argument("--skip-drive", action="store_true", help="(compat) Alias di --no-drive")
    p.add_argument("--skip-push", action="store_true", help="(compat) Salta il push su GitHub")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # 🐳 Pre-check Docker + scelta immediata (prima dello slug)
    tmp_log = Path("output") / "tmp_docker_check.log"
    tmp_log.parent.mkdir(parents=True, exist_ok=True)
    tmp_logger = get_structured_logger("docker_check", log_file=tmp_log)

    pre_skip_preview: Optional[bool] = None
    docker_ok = _docker_available(tmp_logger)
    if not docker_ok:
        if not args.non_interactive:
            ans = _prompt("⚠️  Docker non è attivo o non disponibile. Proseguire senza anteprima? (y/n): ").lower()
            if ans.startswith("y"):
                pre_skip_preview = True
            else:
                raise ConfigError("Anteprima richiesta ma Docker non è disponibile. Avvia Docker e riprova.")
        else:
            pre_skip_preview = True  # non-interactive: prosegue saltando la preview

    # Slug: posizionale? opzionale? → prompt se mancante
    slug = args.slug or args.slug_kw
    if not slug:
        slug = _prompt("🔑 Inserisci lo slug cliente (es: acme-srl): ").strip()

    # Mappatura flag compat
    no_drive = bool(args.no_drive or args.skip_drive)
    force_skip_push = bool(args.skip_push)

    onboarding_full_main(
        slug=slug,
        dry_run=bool(args.dry_run),
        no_drive=no_drive,
        interactive_mode=not bool(args.non_interactive),
        pre_skip_preview=pre_skip_preview,
        force_skip_push=force_skip_push,
    )
