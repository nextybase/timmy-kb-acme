import os
import sys
import argparse
import yaml
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ValidationError

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import BACKUP_SUFFIX, OUTPUT_DIR_NAME
from pipeline.drive_utils import (
    get_drive_service,
    download_drive_pdfs_to_local,
)
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    DriveDownloadError,
    ConversionError,
    PreviewError,
    PushError,
)

from pipeline.utils import is_valid_slug
from pipeline.cleanup import safe_clean_dir
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping

load_dotenv()


def load_client_config(slug: str, base_dir: Path, logger) -> tuple:
    """
    Carica il config.yaml del cliente dalla nuova struttura 'timmy-kb-<slug>' dentro OUTPUT_DIR_NAME.
    """
    client_base_dir = base_dir / OUTPUT_DIR_NAME / f"timmy-kb-{slug}"
    config_path = client_base_dir / "config" / "config.yaml"
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        logger.info(f"📄 Config cliente caricato da: {config_path}")
        return yaml.safe_load(f) or {}, config_path


def onboarding_full_main(slug=None, skip_preview=False, auto_push=False):
    if not slug:
        slug = input("📝 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}.")

    settings = get_settings_for_slug(slug)
    logger = get_structured_logger("onboarding_full", str(settings.logs_path))
    logger.info(f"🚀 Avvio onboarding completo per: {slug}")

    try:
        # Percorsi locali allineati con pre_onboarding
        client_base_dir = settings.base_dir / OUTPUT_DIR_NAME / f"timmy-kb-{slug}"
        raw_dir = client_base_dir / "raw"
        md_output_path = client_base_dir / "book"

        # Caricamento config cliente
        client_config, client_config_path = load_client_config(slug, settings.base_dir, logger)
        drive_folder_id = client_config.get("drive_folder_id")
        if not drive_folder_id:
            raise ConfigError("ID cartella cliente su Drive mancante in config.yaml")

        # Pulizia directory di lavoro
        safe_clean_dir(md_output_path, settings=settings)
        safe_clean_dir(raw_dir, settings=settings)

        # Connessione a Drive e download PDF
        drive_service = get_drive_service(settings)
        download_drive_pdfs_to_local(
            drive_service,
            drive_folder_id,
            raw_dir,
            settings.DRIVE_ID,
            logger
        )

        # Conversione PDF → Markdown
        convert_files_to_structured_markdown(raw_dir, md_output_path, logger)

        # Arricchimento semantico
        mapping = load_semantic_mapping()
        enrich_markdown_folder(md_output_path, mapping, logger)

        # Generazione SUMMARY e README
        generate_summary_markdown(md_output_path, logger)
        generate_readme_markdown(md_output_path, slug, logger)

        # Anteprima GitBook
        if not skip_preview:
            run_gitbook_docker_preview(md_output_path, logger)

        # Push GitHub
        if auto_push:
            push_output_to_github(md_output_path, logger)

        logger.info(f"🏁 Onboarding completo terminato per: {slug}")

    except (PipelineError, ConfigError, DriveDownloadError, ConversionError,
            PreviewError, PushError, ValidationError) as e:
        logger.error(f"❌ Errore onboarding completo: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--skip-preview", action="store_true", help="Salta preview GitBook")
    parser.add_argument("--auto-push", action="store_true", help="Push automatico su GitHub")
    args = parser.parse_args()

    try:
        onboarding_full_main(slug=args.slug, skip_preview=args.skip_preview, auto_push=args.auto_push)
    except PipelineError:
        sys.exit(1)
