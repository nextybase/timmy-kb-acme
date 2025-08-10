import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import (
    get_settings_for_slug,
    is_valid_slug,
    get_client_config
)
from pipeline.drive_utils import (
    get_drive_service,
    download_drive_pdfs_to_local
)
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    DriveDownloadError
)
from pipeline.cleanup_utils import safe_clean_dir
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping

load_dotenv()


def onboarding_full_main(slug=None, skip_preview=False, auto_push=False):
    """
    Procedura di onboarding completa:
    1. Pulizia cartelle locali
    2. Download PDF da Drive
    3. Conversione in Markdown
    4. Arricchimento semantico
    5. Generazione SUMMARY e README
    6. Anteprima GitBook (opzionale)
    7. Push su GitHub (opzionale)
    """
    # Input slug se non passato
    if not slug:
        slug = input("🔧 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}.")

    settings = get_settings_for_slug(slug)
    logger = get_structured_logger("onboarding_full", str(settings.logs_path))
    logger.info(f"🚀 Avvio onboarding completo per: {slug}")

    # Definizione path principali
    raw_dir = settings.raw_dir
    book_dir = settings.book_dir
    logger.info(f"📂 RAW dir: {raw_dir}")
    logger.info(f"📂 BOOK dir: {book_dir}")

    try:
        # Lettura config cliente
        try:
            client_config = get_client_config(slug)
        except ConfigError as e:
            logger.error(f"❌ Config cliente non trovato o invalido: {e}")
            raise

        drive_folder_id = client_config.get("drive_folder_id")
        if not drive_folder_id:
            raise ConfigError("ID cartella Drive mancante nel config cliente.")

        # Pulizia cartelle locali
        safe_clean_dir(raw_dir, settings=settings)
        safe_clean_dir(book_dir, settings=settings)

        # Download PDF da Drive
        drive_service = get_drive_service(settings)
        download_drive_pdfs_to_local(
            service=drive_service,
            drive_folder_id=drive_folder_id,
            local_path=raw_dir,
            shared_drive_id=settings.DRIVE_ID,
            logger=logger
        )

        # Conversione PDF → Markdown
        convert_files_to_structured_markdown(raw_dir, book_dir, logger=logger)

        # Arricchimento semantico
        semantic_mapping = load_semantic_mapping(slug=slug)
        enrich_markdown_folder(book_dir, semantic_mapping, logger=logger)

        # Generazione SUMMARY.md e README.md
        generate_summary_markdown(book_dir, logger=logger)
        generate_readme_markdown(book_dir, logger=logger)

        # Preview GitBook (se non saltato)
        if not skip_preview:
            run_gitbook_docker_preview(book_dir, logger=logger)

        # Push su GitHub (se richiesto)
        if auto_push:
            push_output_to_github(book_dir, slug, logger=logger)

        logger.info(f"✅ Onboarding completo terminato per: {slug}")

    except (PipelineError, ConfigError, DriveDownloadError) as e:
        logger.error(f"❌ Errore onboarding completo: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--skip-preview", action="store_true", help="Salta anteprima GitBook")
    parser.add_argument("--auto-push", action="store_true", help="Esegue push automatico su GitHub")
    args = parser.parse_args()

    try:
        onboarding_full_main(
            slug=args.slug,
            skip_preview=args.skip_preview,
            auto_push=args.auto_push
        )
    except PipelineError:
        sys.exit(1)
