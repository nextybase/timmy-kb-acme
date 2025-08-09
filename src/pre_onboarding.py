import sys
import argparse
import shutil
from pathlib import Path
import yaml

from dotenv import load_dotenv

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug, is_valid_slug
from pipeline.constants import CONFIG_FILE_NAME, BACKUP_SUFFIX
from pipeline.drive_utils import (
    get_drive_service,
    upload_config_to_drive_folder,
    create_drive_folder,
    create_drive_structure_from_yaml,
    create_local_base_structure,
)
from pipeline.exceptions import PipelineError, ConfigError, DriveUploadError

load_dotenv()


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
        logger.info(f"📝 Config aggiornato con ID Drive: {new_data}")
    except Exception as e:
        logger.error(f"❌ Errore aggiornamento config: {e}")
        shutil.copy(backup_path, config_path)
        logger.warning(f"⚠️ Ripristinato config da backup: {backup_path}")
        raise ConfigError(e)


def pre_onboarding_main(slug=None):
    """
    Fase di pre-onboarding: crea struttura locale, struttura Drive e config cliente.
    """
    if not slug:
        slug = input("🔧 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}.")

    settings = get_settings_for_slug(slug)
    logger = get_structured_logger("pre_onboarding", str(settings.logs_path))
    logger.info(f"🚀 Avvio pre-onboarding per: {slug}")

    try:
        yaml_path = Path("config") / "cartelle_raw.yaml"
        template_config_path = Path("config") / CONFIG_FILE_NAME
        if not template_config_path.exists():
            raise ConfigError(f"Template config non trovato: {template_config_path}")

        # Creazione struttura locale completa
        base_dir = create_local_base_structure(slug, yaml_path)

        # Copia template config cliente
        client_config_path = base_dir / "config" / CONFIG_FILE_NAME
        shutil.copy(template_config_path, client_config_path)
        logger.info(f"📄 Config template copiato in: {client_config_path}")

        # Connessione a Drive
        drive_service = get_drive_service(settings)

        # Creazione cartella cliente su Drive
        client_folder_id = create_drive_folder(drive_service, slug, settings.DRIVE_ID)

        # Creazione struttura Drive completa da YAML
        drive_folder_ids = create_drive_structure_from_yaml(drive_service, yaml_path, client_folder_id)

        # Upload config nella cartella cliente su Drive
        upload_config_to_drive_folder(drive_service, client_config_path, client_folder_id, settings.base_dir)

        # Aggiornamento config con ID Drive
        update_config_with_drive_ids(
            client_config_path,
            {
                "drive_folder_id": client_folder_id,
                "drive_raw_folder_id": drive_folder_ids.get("raw"),
                "drive_book_folder_id": drive_folder_ids.get("book"),
                "drive_config_folder_id": client_folder_id,
            },
            logger,
        )

        logger.info(f"✅ Pre-onboarding completato per: {slug}")

    except (PipelineError, ConfigError, DriveUploadError) as e:
        logger.error(f"❌ Errore pre-onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    args = parser.parse_args()

    try:
        pre_onboarding_main(slug=args.slug)
    except PipelineError:
        sys.exit(1)
