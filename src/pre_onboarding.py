import sys
import argparse
import shutil
from pathlib import Path
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import BACKUP_SUFFIX
from pipeline.drive_utils import (
    get_drive_service,
    upload_config_to_drive_folder,
    create_drive_folder,
    create_drive_structure_from_yaml,
    create_local_base_structure,
    list_drive_files,  # 🔹 Serve per cercare file già presenti
    delete_drive_file  # 🔹 Serve per eliminare file già presenti
)
from pipeline.exceptions import PipelineError, ConfigError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath, sanitize_filename


def update_config_with_drive_ids(context: ClientContext, new_data: dict, logger) -> None:
    """Aggiorna config cliente con nuovi dati e backup."""
    config_path = context.config_path
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")

    if not is_safe_subpath(config_path, context.base_dir):
        raise ConfigError(f"Path config non sicuro: {config_path}")

    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    logger.info(f"💾 Backup config creato: {backup_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}
    config_data.update(new_data)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, allow_unicode=True)

    logger.info(f"✅ Config aggiornato con dati: {new_data}")


def ensure_cartelle_raw_yaml_exists(yaml_path: Path, logger):
    """Crea il file YAML struttura cartelle se non esiste."""
    if yaml_path.exists():
        return

    template_path = Path("config") / "cartelle_raw_template.yaml"
    if template_path.exists():
        shutil.copy(template_path, yaml_path)
        logger.info(f"📄 File YAML struttura cartelle creato da template: {yaml_path}")
    else:
        default_content = {"raw": []}
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(default_content, f, sort_keys=False, allow_unicode=True)
        logger.info(f"📄 File YAML struttura cartelle creato con struttura minima: {yaml_path}")


def pre_onboarding_main(slug: str, client_name: str = None, no_interactive: bool = False, dry_run: bool = False):
    """Esegue il pre-onboarding del cliente specificato."""
    # Logger strutturato creato qui e passato al ClientContext
    logger = get_structured_logger("pre_onboarding")
    context = ClientContext.load(slug, logger=logger)
    logger.info(f"🚀 Avvio pre-onboarding per cliente: {context.slug}")

    try:
        # Fix percorso YAML
        structure_file = context.settings.get("local_structure_file", "cartelle_raw.yaml")
        if structure_file.startswith("config/"):
            structure_file = structure_file.replace("config/", "")
            logger.warning(f"⚠️ Corretto percorso local_structure_file: {structure_file}")

        yaml_path = Path("config") / structure_file
        ensure_cartelle_raw_yaml_exists(yaml_path, logger)

        # ✅ Creazione struttura locale sempre
        create_local_base_structure(context, yaml_path)

        if dry_run:
            logger.info("💡 Modalità dry-run attiva: struttura locale creata, nessuna interazione con Drive.")
            return

        # Connessione a Drive
        drive_service = get_drive_service(context)

        # Creazione cartella cliente su Drive
        client_folder_id = create_drive_folder(
            drive_service, sanitize_filename(context.slug), context.env.get("DRIVE_ID")
        )
        logger.info(f"📂 Cartella cliente creata su Drive: {client_folder_id}")

        # Creazione struttura su Drive
        drive_folder_ids = create_drive_structure_from_yaml(drive_service, yaml_path, client_folder_id)
        logger.info(f"📂 Struttura Drive creata: {drive_folder_ids}")

        # Controllo cartella RAW
        raw_folder_id = drive_folder_ids.get("raw")
        if not raw_folder_id:
            raise PipelineError("Cartella RAW non trovata su Drive: verifica YAML di struttura cartelle.")

        # 🔹 Sovrascrittura manuale config.yaml su Drive
        existing_files = list_drive_files(drive_service, client_folder_id, query="name='config.yaml'")
        for f in existing_files:
            delete_drive_file(drive_service, f["id"])
            logger.info(f"🗑️ Config precedente rimosso da Drive: {f['id']}")

        # 📤 Upload config.yaml su Drive
        file_id = upload_config_to_drive_folder(drive_service, context, client_folder_id)
        logger.info(f"📤 Config caricato su Drive con ID: {file_id}")

        # Aggiornamento config cliente
        update_config_with_drive_ids(
            context,
            {
                "drive_folder_id": client_folder_id,
                "drive_raw_folder_id": raw_folder_id,
                "drive_config_folder_id": client_folder_id,
                "client_name": client_name or "",
            },
            logger,
        )

        logger.info(f"✅ Pre-onboarding completato per cliente: {context.slug}")

    except (PipelineError, ConfigError) as e:
        logger.error(f"❌ Errore pre-onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB (v1.0 stable)")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--name", type=str, help="Nome completo cliente (es: Acme S.r.l.)")
    parser.add_argument("--no-interactive", action="store_true", help="Esegue senza input manuali")
    parser.add_argument("--dry-run", action="store_true", help="Solo struttura locale senza Drive")
    args = parser.parse_args()

    if not args.slug:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()
    if not args.name and not args.no_interactive:
        args.name = input("🔹 Inserisci il nome cliente (es: Acme S.r.l.): ").strip()

    try:
        pre_onboarding_main(
            slug=args.slug,
            client_name=args.name,
            no_interactive=args.no_interactive,
            dry_run=args.dry_run
        )
    except PipelineError:
        sys.exit(1)
