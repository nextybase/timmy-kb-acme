# src/onboarding_full.py
"""
Onboarding completo Timmy-KB:
1. Pulizia cartelle locali
2. Download PDF da Drive
3. Conversione in Markdown
4. Arricchimento semantico
5. Generazione README e SUMMARY
6. Preview GitBook (opzionale)
7. Push su GitHub (opzionale)

Refactor v1.0:
- Uso esclusivo di ClientContext
- Eliminato get_settings_for_slug
- CLI con --skip-preview, --auto-push e modalità interattiva per slug
- Controllo config.yaml in modalità interattiva
"""

import sys
import argparse
from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.cleanup_utils import safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.exceptions import PipelineError, ConfigError, DriveDownloadError
from pipeline.context import ClientContext


def onboarding_full_main(slug: str, skip_preview: bool = False, auto_push: bool = False):
    """
    Esegue la procedura di onboarding completa per il cliente indicato.
    """
    # Carica contesto
    context = ClientContext.load(slug)
    logger = get_structured_logger("onboarding_full", context=context)
    logger.info(f"🚀 Avvio onboarding completo per: {context.slug}")

    try:
        # 1. Pulizia cartelle
        safe_clean_dir(context.raw_dir, context=context)
        safe_clean_dir(context.book_dir, context=context)

        # 2. Download PDF da Drive
        drive_service = get_drive_service(context)
        download_drive_pdfs_to_local(
            service=drive_service,
            drive_folder_id=context.settings.get("drive_folder_id"),
            local_path=context.raw_dir,
            shared_drive_id=context.settings.get("DRIVE_ID"),
            logger=logger
        )

        # 3. Conversione in Markdown
        convert_files_to_structured_markdown(context, log=logger)

        # 4. Arricchimento semantico
        semantic_mapping = load_semantic_mapping(context, logger=logger)
        enrich_markdown_folder(context, logger=logger)

        # 5. Generazione SUMMARY.md e README.md
        generate_summary_markdown(context, log=logger)
        generate_readme_markdown(context, log=logger)

        # 6. Anteprima GitBook (opzionale)
        if not skip_preview:
            run_gitbook_docker_preview(context)

        # 7. Push su GitHub (opzionale)
        if not auto_push:
            resp = input("📤 Vuoi fare il push su GitHub? [y/N]: ").strip().lower()
            if resp == "y":
                auto_push = True

        if auto_push:
            push_output_to_github(context)

        logger.info(f"✅ Onboarding completato per: {context.slug}")

    except (PipelineError, ConfigError, DriveDownloadError) as e:
        logger.error(f"❌ Errore onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"💥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--skip-preview", action="store_true", help="Salta anteprima GitBook")
    parser.add_argument("--auto-push", action="store_true", help="Esegue push automatico su GitHub")
    parser.add_argument("--skip-interactive", action="store_true", help="Salta richieste interattive (test/CI)")
    args = parser.parse_args()

    # Modalità interattiva se slug non fornito e skip-interactive non attivo
    if not args.slug and not args.skip_interactive:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()

    # Controllo esistenza config.yaml in modalità interattiva
    config_path = Path(__file__).resolve().parents[1] / "output" / f"timmy-kb-{args.slug}" / "config" / "config.yaml"
    if not config_path.exists():
        print(f"⚠️ Config file non trovato per slug '{args.slug}'. Assicurati di aver completato il pre-onboarding.")
        sys.exit(1)

    try:
        onboarding_full_main(
            slug=args.slug,
            skip_preview=args.skip_preview,
            auto_push=args.auto_push
        )
    except PipelineError:
        sys.exit(1)
