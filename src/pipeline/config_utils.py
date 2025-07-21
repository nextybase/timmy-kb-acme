# src/pipeline/config_utils.py

import os
import yaml
import tempfile
from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import get_drive_service, find_drive_folder_by_name
from googleapiclient.http import MediaFileUpload

logger = get_structured_logger("pipeline.config_utils")

def load_client_config(slug: str) -> dict:
    """
    Carica e arricchisce la configurazione del cliente dallo YAML.
    Se mancano drive_id o cliente_folder_id, li recupera dinamicamente.
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    logger.debug(f"Caricamento config da: {config_path}")
    if not config_path.exists():
        logger.error(f"❌ File config.yaml non trovato per il cliente '{slug}'")
        raise FileNotFoundError(f"❌ File config.yaml non trovato per il cliente '{slug}'")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Integrazione valori base
    config["slug"] = slug
    config["nome_cliente"] = config.get("cliente_nome", slug)

    # Definizione percorsi locali
    config["raw_dir"] = f"tmp/timmykb_rawpdf_{slug}"
    config["output_path"] = f"output/timmy-kb-{slug}"
    config["md_output_path"] = config["output_path"]
    config["github_repo"] = f"timmy-kb-{slug}"

    # Recupero Drive ID se mancante
    if not config.get("drive_id"):
        config["drive_id"] = os.getenv("DRIVE_ID")
        logger.warning(f"⚠️ drive_id non presente in config, usato valore da .env: {config['drive_id']}")

    # Recupero ID cartella cliente se mancante
    if not config.get("cliente_folder_id"):
        try:
            service = get_drive_service()
            folder = find_drive_folder_by_name(service, slug, drive_id=config["drive_id"])
            if folder:
                config["cliente_folder_id"] = folder["id"]
                logger.info(f"📂 Cartella cliente trovata: {folder['id']}")
            else:
                raise ValueError(f"❌ Cartella '{slug}' non trovata nel Drive ID {config['drive_id']}")
        except Exception as e:
            logger.error(f"❌ Errore durante il recupero della cartella cliente: {e}")
            raise e

    logger.debug(f"Config caricata: {config}")
    return config

def generate_client_config_dict(slug: str, nome: str) -> dict:
    """
    Genera un dizionario di configurazione di base per il cliente.
    """
    logger.debug(f"Generazione config dict per slug: {slug}, nome: {nome}")
    return {
        'cliente_id': slug,
        'cliente_nome': nome
    }

def upload_config_to_drive_folder(service, folder_id: str, config_data: dict):
    """
    Carica il file config.yaml su Google Drive.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml", mode='w', encoding='utf-8') as temp_file:
            yaml.dump(config_data, temp_file, allow_unicode=True)
            temp_file_path = temp_file.name

        media = MediaFileUpload(temp_file_path, mimetype='application/x-yaml', resumable=False)
        file_metadata = {
            'name': 'config.yaml',
            'parents': [folder_id]
        }

        service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        logger.info("✅ File config.yaml caricato con successo su Google Drive.")
        logger.debug(f"📄 Il file temporaneo resta disponibile: {temp_file_path}")

    except Exception as e:
        logger.error(f"❌ Errore durante il caricamento su Drive: {e}")
        raise e

def write_client_config_file(config_data: dict, path: Path) -> None:
    """
    Scrive il file config.yaml localmente per verifica/rollback.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
        logger.info(f"✅ File di configurazione salvato in locale: {path}")
    except Exception as e:
        logger.error(f"❌ Errore nella scrittura locale: {e}")
        raise e
