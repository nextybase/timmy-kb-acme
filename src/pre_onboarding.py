# src/pre_onboarding.py
"""
Procedura di pre-onboarding Timmy-KB:
- Crea struttura locale cliente
- Crea struttura cartelle su Google Drive
- Copia file di configurazione e mapping semantico
- Aggiorna config.yaml con ID Drive

Refactor v1.0:
- Uso esclusivo di ClientContext
- Eliminato get_settings_for_slug
- CLI con opzioni --no-interactive e --dry-run
- Modalità interattiva se non in fase test
"""

import sys
import argparse
import shutil
from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import CONFIG_FILE_NAME, BACKUP_SUFFIX
from pipeline.drive_utils import (
    get_drive_service,
    upload_config_to_drive_folder,
    create_drive_folder,
    create_drive_structure_from_yaml,
    create_local_base_structure,
)
from pipeline.exceptions import PipelineError, ConfigError, DriveUploadError
from pipeline.context import ClientContext


def update_config_with_drive_ids(context: ClientContext, new_data: dict, logger) -> None:
    """
    Aggiorna il config.yaml del cliente con i nuovi dati Drive, mantenendo un backup sicuro.
    """
    config_path = context.config_file
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")

    backup_path = config_path.with_suffix(BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    logger.info(f"📦 Backup config creato: {backup_path}")

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
        logger.warning(f"↩️ Ripristinato config dal backup: {backup_path}")
        raise ConfigError(e)


def pre_onboarding_main(slug: str, no_interactive: bool = False, dry_run: bool = False):
    """
    Esegue il pre-onboarding del cliente specificato.
    """
    # Carica contesto cliente
    context = ClientContext.load(slug)
    logger = get_structured_logger("pre_onboarding", context=context)
    logger.info(f"🚀 Avvio pre-onboarding per cliente: {context.slug}")

    try:
        # Legge il file YAML della struttura locale dal config cliente
        structure_file = context.settings.get("local_structure_file", "cartelle_raw.yaml")
        local_structure_yaml = Path("config") / structure_file

        # Creazione struttura locale
        base_dir = create_local_base_structure(context, local_structure_yaml)
        logger.info(f"📂 Struttura locale creata: {base_dir}")

        # Copia config template
        template_config_path = Path("config") / CONFIG_FILE_NAME
        if not template_config_path.exists():
            raise ConfigError(f"Template config non trovato: {template_config_path}")
        shutil.copy(template_config_path, context.config_file)
        logger.info(f"📄 Config template copiato in: {context.config_file}")

        # Copia mapping semantico se esiste
        global_mapping_path = Path("config") / "semantic_mapping.yaml"
        if global_mapping_path.exists():
            shutil.copy(global_mapping_path, context.config_dir / "semantic_mapping.yaml")
            logger.info(f"📄 Mapping semantico copiato in: {context.config_dir / 'semantic_mapping.yaml'}")
        else:
            logger.warning("⚠️ Nessun mapping semantico globale trovato.")

        if dry_run:
            logger.info("🧪 Modalità dry-run attiva. Interrompo prima di interagire con Drive.")
            return

        # Connessione a Drive
        drive_service = get_drive_service(context)

        # Creazione cartella cliente su Drive
        client_folder_id = create_drive_folder(drive_service, context.slug, context.settings.DRIVE_ID)
        logger.info(f"📂 Cartella cliente su Drive creata: {client_folder_id}")

        # Creazione struttura su Drive da YAML
        yaml_path = Path("config") / "cartelle_raw.yaml"
        drive_folder_ids = create_drive_structure_from_yaml(drive_service, yaml_path, client_folder_id)

        # Upload config.yaml su Drive
        upload_config_to_drive_folder(drive_service, context.config_file, client_folder_id, context.base_dir)

        # Aggiornamento config locale con ID Drive
        update_config_with_drive_ids(
            context,
            {
                "drive_folder_id": client_folder_id,
                "drive_raw_folder_id": drive_folder_ids.get("raw"),
                "drive_book_folder_id": drive_folder_ids.get("book"),
                "drive_config_folder_id": client_folder_id,
            },
            logger,
        )

        logger.info(f"✅ Pre-onboarding completato per cliente: {context.slug}")

    except (PipelineError, ConfigError, DriveUploadError) as e:
        logger.error(f"❌ Errore pre-onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"💥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--no-interactive", action="store_true", help="Salta richieste interattive")
    parser.add_argument("--dry-run", action="store_true", help="Esegui solo parte locale senza interazione con Drive")
    args = parser.parse_args()

    # Modalità interattiva se slug non fornito e no-interactive non attivo
    if not args.slug and not args.no_interactive:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()
        customer_name = input("🔹 Inserisci il nome completo del cliente: ").strip()

        # Creazione cartella config senza usare ClientContext.load()
        config_dir = Path(__file__).resolve().parents[1] / "output" / f"timmy-kb-{args.slug}" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Creazione config.yaml base con il nome cliente
        config_path = config_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"client_name": customer_name}, f, allow_unicode=True)
        print(f"📄 Salvato nome cliente in {config_path}")

    try:
        pre_onboarding_main(
            slug=args.slug,
            no_interactive=args.no_interactive,
            dry_run=args.dry_run
        )
    except PipelineError:
        sys.exit(1)
