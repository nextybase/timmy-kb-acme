import os
import yaml
import tempfile
from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import get_drive_service
from pipeline.exceptions import ConfigError

logger = get_structured_logger("pipeline.config_utils")

def load_client_config(slug: str) -> dict:
    """
    Carica la configurazione del cliente dallo YAML.
    Deve essere presente drive_folder_id; in caso contrario errore (ConfigError).
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    logger.debug(f"Caricamento config da: {config_path}")
    if not config_path.exists():
        logger.error(f"❌ File config.yaml non trovato per il cliente '{slug}'")
        raise ConfigError(f"File config.yaml non trovato per il cliente '{slug}'")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore durante la lettura del file config.yaml: {e}")
        raise ConfigError(f"Errore nella lettura del file config.yaml: {e}")

    config["slug"] = slug
    config["nome_cliente"] = config.get("cliente_nome", slug)
    config["raw_dir"] = f"tmp/timmykb_rawpdf_{slug}"
    config["output_path"] = f"output/timmy-kb-{slug}"
    config["md_output_path"] = config["output_path"]
    config["github_repo"] = f"timmy-kb-{slug}"

    if not config.get("drive_id"):
        config["drive_id"] = os.getenv("DRIVE_ID")
        logger.warning(f"⚠️ drive_id non presente in config, usato valore da .env: {config['drive_id']}")

    if not config.get("drive_folder_id"):
        logger.error("❌ drive_folder_id mancante in config: impossibile procedere.")
        raise ConfigError("drive_folder_id mancante in config. Esegui prima il pre-onboarding.")

    logger.info(f"✅ Config caricata correttamente per il cliente: {slug}")
    logger.debug(f"Config caricata: {config}")
    return config

def upload_config_to_drive_folder(service, folder_id: str, config_data: dict):
    """
    Carica il file config.yaml su Google Drive.
    Solleva ConfigError in caso di errore.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml", mode='w', encoding='utf-8') as temp_file:
            yaml.dump(config_data, temp_file, allow_unicode=True)
            temp_file_path = temp_file.name

        from googleapiclient.http import MediaFileUpload
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
        raise ConfigError(f"Errore durante il caricamento su Drive: {e}")

def write_client_config_file(config_data: dict, path: Path) -> None:
    """
    Scrive il file config.yaml localmente per verifica/rollback.
    Solleva ConfigError in caso di errore.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
        logger.info(f"✅ File di configurazione salvato in locale: {path}")
    except Exception as e:
        logger.error(f"❌ Errore nella scrittura locale: {e}")
        raise ConfigError(f"Errore nella scrittura locale: {e}")
