#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

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


def onboarding_full_main(
    slug: str,
    *,
    dry_run: bool = False,
    no_drive: bool = False,
    interactive_mode: bool = True,
) -> None:
    """
    Onboarding completo per <slug>:
      1) Validazione config
      2) (opz.) Download PDF da Drive → output/<slug>/raw/
      3) Conversione PDF→Markdown per cartella → output/<slug>/book/*.md
      4) Generazione SUMMARY.md e README.md in book/
      5) Preview Honkit (Docker)
      6) (opz.) Push su GitHub
    """
    # Logger unificato su file cliente
    log_file = Path("output") / f"timmy-kb-{slug}" / "logs" / "onboarding.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("onboarding_full", log_file=log_file)

    try:
        # Caricamento contesto
        context: ClientContext = ClientContext.load(slug=slug, interactive=interactive_mode)
        logger.info(f"Config cliente caricata: {context.config_path}")
        logger.info("🚀 Avvio onboarding completo")

        # 1) Validazione configurazione cliente
        logger.info("📑 Validazione configurazione cliente...")
        cfg = get_client_config(context) or {}
        if not dry_run and not no_drive:
            if not cfg.get("drive_raw_folder_id"):
                raise ConfigError("Config mancante di 'drive_raw_folder_id' (pre_onboarding non completato?)")
        logger.info("✅ Configurazione cliente valida")

        # 2) Download PDF da Google Drive
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
            logger.info("⏭️  Download da Drive saltato (dry-run o --no-drive)")

        # 3) Conversione PDF → Markdown
        logger.info("📄 Avvio conversione PDF in Markdown...")
        convert_files_to_structured_markdown(context)
        logger.info("✅ Conversione completata")

        # 4) SUMMARY.md + README.md
        logger.info("📝 Generazione SUMMARY.md e README.md...")
        generate_summary_markdown(context)
        generate_readme_markdown(context)
        logger.info("✅ SUMMARY.md e README.md generati")

        # 5) Preview Honkit (Docker)
        logger.info("🌐 Avvio anteprima GitBook...")
        ensure_book_json(book_dir=Path(context.md_dir), slug=context.slug)
        ensure_package_json(book_dir=Path(context.md_dir), slug=context.slug)
        run_gitbook_docker_preview(context=context, port=4000, container_name="honkit_preview", wait_on_exit=True)
        logger.info("✅ Anteprima GitBook completata")

        # 6) Push GitHub (opzionale)
        logger.info("📤 Avvio push su GitHub...")
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
            logger.info("⏭️  Push GitHub saltato")

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
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--dry-run", action="store_true", help="Salta Drive e GitHub; esegue solo conversione/preview")
    p.add_argument("--no-drive", action="store_true", help="Non scarica da Drive (usa PDF già presenti in raw/)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt (skip push)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    slug = args.slug or _prompt("🔑 Inserisci lo slug cliente (es: acme-srl): ").strip()
    onboarding_full_main(
        slug=slug,
        dry_run=bool(args.dry_run),
        no_drive=bool(args.no_drive),
        interactive_mode=not bool(args.non_interactive),
    )
