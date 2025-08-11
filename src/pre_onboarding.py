# src/pre_onboarding.py (versione debug)

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
from pipeline.path_utils import is_safe_subpath, sanitize_filename


def update_config_with_drive_ids(context: ClientContext, new_data: dict, logger) -> None:
    """Aggiorna il config.yaml del cliente con i nuovi dati, mantenendo un backup sicuro."""
    print(f"[DEBUG] Aggiornamento config con dati: {new_data}")
    config_path = context.config_path
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")

    if not is_safe_subpath(config_path, context.base_dir):
        raise ConfigError(f"Path config non sicuro: {config_path}")

    backup_path = config_path.with_suffix(BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    logger.info(f"📦 Backup config creato: {backup_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}
    config_data.update(new_data)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, allow_unicode=True)
    logger.info(f"📝 Config aggiornato con dati: {new_data}")


def pre_onboarding_main(slug: str, client_name: str = None, no_interactive: bool = False, dry_run: bool = False):
    """Esegue il pre-onboarding del cliente specificato."""
    print(f"[DEBUG] Avvio pre_onboarding_main: slug={slug}, client_name={client_name}, dry_run={dry_run}")

    context = ClientContext.load(slug)
    logger = get_structured_logger("pre_onboarding", context=context)
    logger.info(f"🚀 Avvio pre-onboarding per cliente: {context.slug}")

    try:
        structure_file = context.settings.get("local_structure_file", "cartelle_raw.yaml")
        yaml_path = Path("config") / structure_file
        print(f"[DEBUG] Uso file struttura: {yaml_path}")

        base_dir = create_local_base_structure(context, yaml_path)
        print(f"[DEBUG] Struttura locale creata in: {base_dir}")

        template_config_path = Path("config") / CONFIG_FILE_NAME
        if not template_config_path.exists():
            raise ConfigError(f"Template config non trovato: {template_config_path}")
        shutil.copy(template_config_path, context.config_path)
        print(f"[DEBUG] Config template copiato in: {context.config_path}")

        global_mapping_path = Path("config") / "semantic_mapping.yaml"
        target_mapping_path = context.config_path.parent / "semantic_mapping.yaml"
        if global_mapping_path.exists():
            shutil.copy(global_mapping_path, target_mapping_path)
            print(f"[DEBUG] Mapping semantico copiato: {target_mapping_path}")
        else:
            default_mapping_path = Path("config") / "default_semantic_mapping.yaml"
            if default_mapping_path.exists():
                shutil.copy(default_mapping_path, target_mapping_path)
                print("[DEBUG] Mapping globale mancante: uso default")
            else:
                print("[DEBUG] Nessun mapping trovato (globale o default)")

        if dry_run:
            print("[DEBUG] Modalità dry-run attiva → interruzione prima di Drive")
            return

        drive_service = get_drive_service(context)
        print("[DEBUG] Connessione a Google Drive ok")

        client_folder_id = create_drive_folder(
            drive_service, sanitize_filename(context.slug), context.env.get("DRIVE_ID")
        )
        print(f"[DEBUG] Cartella cliente su Drive creata: {client_folder_id}")

        drive_folder_ids = create_drive_structure_from_yaml(drive_service, yaml_path, client_folder_id)
        print(f"[DEBUG] Struttura Drive creata: {drive_folder_ids}")

        upload_config_to_drive_folder(drive_service, context, client_folder_id)
        print("[DEBUG] Config caricato su Drive")

        update_config_with_drive_ids(
            context,
            {
                "drive_folder_id": client_folder_id,
                "drive_raw_folder_id": drive_folder_ids.get("raw"),
                "drive_book_folder_id": drive_folder_ids.get("book"),
                "drive_config_folder_id": client_folder_id,
                "client_name": client_name or "",
            },
            logger,
        )

        print("[DEBUG] Pre-onboarding completato con successo")

    except Exception as e:
        print(f"[ERRORE] {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB (DEBUG)")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--client-name", type=str, help="Nome cliente (es: Acme S.r.l.)")
    parser.add_argument("--no-interactive", action="store_true", help="Salta richieste interattive")
    parser.add_argument("--dry-run", action="store_true", help="Esegui solo parte locale senza interazione con Drive")
    args = parser.parse_args()

    if not args.slug and not args.no_interactive:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()
    if not args.client_name and not args.no_interactive:
        args.client_name = input("🔹 Inserisci il nome cliente (es: Acme S.r.l.): ").strip()

    try:
        pre_onboarding_main(
            slug=args.slug,
            client_name=args.client_name,
            no_interactive=args.no_interactive,
            dry_run=args.dry_run
        )
    except PipelineError:
        sys.exit(1)
