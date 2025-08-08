import os
import sys
import argparse
import yaml
import shutil
from pathlib import Path

from dotenv import load_dotenv

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import CONFIG_FILE_NAME, BACKUP_SUFFIX, RAW_DIR_NAME, BOOK_DIR_NAME, CONFIG_DIR_NAME
from pipeline.drive_utils import (
    get_drive_service,
    create_drive_folder,
    upload_config_to_drive_folder,
    drive_api_call,
)
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    DriveUploadError,
)
from pipeline.utils import is_valid_slug

load_dotenv()


def validate_and_create_dir(path: Path, base_dir: Path, logger) -> None:
    """
    Valida che la directory sia sotto BASE_DIR e crea se mancante.
    """
    path = path.resolve()
    if not str(path).startswith(str(base_dir.resolve())):
        raise PipelineError(f"Creazione bloccata: {path} non è sotto BASE_DIR")
    path.mkdir(parents=True, exist_ok=True)
    logger.info(f"📂 Directory valida: {path}")


def update_config_with_drive_ids(config_path: Path, new_data: dict, logger) -> None:
    """
    Aggiorna il config cliente con i nuovi dati Drive, con backup sicuro.
    """
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")

    backup_path = config_path.with_suffix(BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    logger.info(f"💾 Backup config creato: {backup_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
        config_data.update(new_data)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, allow_unicode=True)
        logger.info(f"✅ Config aggiornato con ID Drive: {new_data}")
    except Exception as e:
        logger.error(f"❌ Errore aggiornamento config: {e}")
        shutil.copy(backup_path, config_path)
        logger.warning(f"🔄 Ripristinato config da backup: {backup_path}")
        raise ConfigError(e)


def pre_onboarding_main(slug=None):
    """
    Fase di pre-onboarding: crea config cliente e struttura Drive.
    """
    if not slug:
        slug = input("📝 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}.")

    settings = get_settings_for_slug(slug)
    logger = get_structured_logger("pre_onboarding", str(settings.logs_path))
    logger.info(f"🚀 Avvio pre-onboarding per: {slug}")

    try:
        # Creazione cartelle locali sicura
        validate_and_create_dir(settings.output_dir, settings.base_dir, logger)
        validate_and_create_dir(settings.raw_dir, settings.base_dir, logger)
        validate_and_create_dir(settings.md_output_path, settings.base_dir, logger)
        validate_and_create_dir(settings.config_dir, settings.base_dir, logger)

        # Copia template config cliente
        template_config_path = Path("config") / CONFIG_FILE_NAME
        if not template_config_path.exists():
            raise ConfigError(f"Template config non trovato: {template_config_path}")

        client_config_path = settings.config_dir / CONFIG_FILE_NAME
        shutil.copy(template_config_path, client_config_path)
        logger.info(f"📄 Config template copiato in: {client_config_path}")

        # Connessione Drive
        drive_service = get_drive_service(settings)

        # Creazione cartella cliente su Drive
        client_folder_id = drive_api_call(
            create_drive_folder,
            service=drive_service,
            name=slug,
            parent_id=settings.DRIVE_ID  # Shared Drive root
        )

        # Creazione sottocartelle su Drive
        raw_folder_id = drive_api_call(create_drive_folder, service=drive_service, name=RAW_DIR_NAME, parent_id=client_folder_id)
        book_folder_id = drive_api_call(create_drive_folder, service=drive_service, name=BOOK_DIR_NAME, parent_id=client_folder_id)
        config_folder_id = drive_api_call(create_drive_folder, service=drive_service, name=CONFIG_DIR_NAME, parent_id=client_folder_id)

        # Upload config su Drive (dentro la sottocartella config)
        drive_api_call(
            upload_config_to_drive_folder,
            service=drive_service,
            config_path=client_config_path,
            folder_id=config_folder_id,
            base_dir=settings.base_dir
        )

        # Aggiornamento config con ID Drive
        update_config_with_drive_ids(client_config_path, {
            "drive_folder_id": client_folder_id,
            "drive_raw_folder_id": raw_folder_id,
            "drive_book_folder_id": book_folder_id,
            "drive_config_folder_id": config_folder_id
        }, logger)

        logger.info(f"🏁 Pre-onboarding completato per: {slug}")

    except (PipelineError, ConfigError, DriveUploadError) as e:
        logger.error(f"❌ Errore pre-onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"🔥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    args = parser.parse_args()

    try:
        pre_onboarding_main(slug=args.slug)
    except PipelineError:
        sys.exit(1)
