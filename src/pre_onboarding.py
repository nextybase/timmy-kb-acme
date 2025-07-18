import sys
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

from utils.drive_utils import get_drive_service, create_folder
from utils.config_writer import generate_config_yaml, write_config, upload_config_to_drive

# === SETUP LOGGING E ENV ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
SHARED_DRIVE_ID = os.getenv("DRIVE_ID")      # Unificato: sempre DRIVE_ID
LOCAL_TEMP_CONFIG_PATH = Path(os.getenv("LOCAL_TEMP_CONFIG_PATH", "temp_config/config.yaml"))
CARTELLE_RAW_YAML = Path(os.getenv("CARTELLE_RAW_YAML", "config/cartelle_raw.yaml"))

def validate_folders_yaml(yaml_path: Path) -> list:
    """
    Valida che la struttura cartelle sia compatibile:
    root_folders deve essere una lista di dict con almeno la chiave 'name'.
    Ritorna la lista di root_folders oppure None in caso di errore.
    """
    if not yaml_path.exists():
        logger.error(f"❌ File YAML non trovato: {yaml_path}")
        return None
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        folders = data.get("root_folders", None)
        if not isinstance(folders, list):
            logger.error("❌ 'root_folders' deve essere una lista.")
            return None
        for idx, item in enumerate(folders):
            if not isinstance(item, dict) or "name" not in item:
                logger.error(f"❌ Ogni elemento di 'root_folders' deve essere un dict con chiave 'name'. Errore al n°{idx+1}")
                return None
        logger.info("✅ Struttura cartelle valida.")
        return folders
    except Exception as e:
        logger.error(f"❌ Errore durante la validazione YAML cartelle: {e}")
        return None

def run_preonboarding(slug: str, nome: str,
                      cartelle_yaml: Path = CARTELLE_RAW_YAML,
                      temp_config_path: Path = LOCAL_TEMP_CONFIG_PATH,
                      drive_id: str = SHARED_DRIVE_ID):
    logger.info("👤 Pre-onboarding Timmy-KB")
    config_data = generate_config_yaml(slug, nome)
    write_config(config_data, temp_config_path)
    logger.info(f"📝 File di configurazione generato e salvato in: {temp_config_path.resolve()}")

    conferma = input("✅ Confermi il caricamento su Drive e la creazione struttura? [y/n]: ").strip().lower()
    if conferma != 'y':
        logger.info("❌ Operazione annullata. Pulizia file temporanei...")
        try:
            temp_config_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"⚠️  Errore durante la rimozione del file temporaneo: {e}")
        return False

    # --- Validazione YAML struttura cartelle ---
    folders = validate_folders_yaml(cartelle_yaml)
    if folders is None:
        logger.error("❌ Struttura cartelle non valida. Uscita.")
        return False

    try:
        service = get_drive_service()
    except Exception as e:
        logger.error(f"❌ Errore nella creazione del servizio Drive: {e}")
        return False

    try:
        folder_id = create_folder(service, name=slug, parent_id=drive_id)
        logger.info(f"📁 Cartella cliente '{slug}' creata con id: {folder_id}")
    except Exception as e:
        logger.error(f"❌ Errore nella creazione cartella principale su Drive: {e}")
        return False

    try:
        upload_config_to_drive(service, folder_id, config_data)
        logger.info(f"✅ File config.yaml caricato su Drive per cliente '{slug}'.")
    except Exception as e:
        logger.error(f"❌ Errore upload config.yaml su Drive: {e}")
        return False

    # --- Creazione struttura cartelle e subcartelle ---
    for root in folders:
        root_name = root.get("name")
        subfolders = root.get("subfolders", [])
        try:
            root_id = create_folder(service, name=root_name, parent_id=folder_id)
            logger.info(f"📁 Cartella creata: {root_name} (id: {root_id})")
            for sub in subfolders:
                try:
                    sub_id = create_folder(service, name=sub, parent_id=root_id)
                    logger.info(f"  └─ 📁 Sottocartella: {sub} (id: {sub_id})")
                except Exception as sub_e:
                    logger.warning(f"⚠️  Errore creazione sottocartella '{sub}': {sub_e}")
        except Exception as root_e:
            logger.warning(f"⚠️  Errore creazione cartella '{root_name}': {root_e}")

    logger.info("✅ Pre-onboarding completato con successo.")
    return True

if __name__ == "__main__":
    slug = input("🔤 Slug cliente: ").strip().lower()
    nome = input("📝 Nome cliente: ").strip()
    run_preonboarding(slug, nome)
