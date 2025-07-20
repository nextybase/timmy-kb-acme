import os
import yaml
from pathlib import Path
from utils.logger_utils import get_logger
from utils.drive_utils import get_drive_service, find_folder_by_name

logger = get_logger("config_loader")

def load_config(slug: str) -> dict:
    """
    Carica e arricchisce la configurazione del cliente dallo YAML.
    Se mancano drive_id o cliente_folder_id, li recupera dinamicamente.
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"❌ File config.yaml non trovato per il cliente '{slug}'")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Integrazione valori base
    config["slug"] = slug
    config["nome_cliente"] = config.get("cliente_nome", slug)

    # Definizione percorsi locali
    config["raw_dir"] = f"tmp/timmykb_rawpdf_{slug}"
    config["output_path"] = f"output/timmy-kb-{slug}"
    config["md_output_path"] = config["output_path"]  # Alias per chiarezza
    config["github_repo"] = f"timmy-kb-{slug}"

    # Recupero Drive ID se mancante
    if not config.get("drive_id"):
        config["drive_id"] = os.getenv("DRIVE_ID")
        logger.warning(f"⚠️ drive_id non presente in config, usato valore da .env: {config['drive_id']}")

    # Recupero ID cartella cliente se mancante
    if not config.get("cliente_folder_id"):
        try:
            service = get_drive_service()
            folder = find_folder_by_name(service, slug, drive_id=config["drive_id"])
            if folder:
                config["cliente_folder_id"] = folder["id"]
                logger.info(f"📂 Cartella cliente trovata: {folder['id']}")
            else:
                raise ValueError(f"❌ Cartella '{slug}' non trovata nel Drive ID {config['drive_id']}")
        except Exception as e:
            logger.error(f"❌ Errore durante il recupero della cartella cliente: {e}")
            raise e

    return config
