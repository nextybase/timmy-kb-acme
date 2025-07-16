# src/pre_onboarding.py

import sys
import yaml
import logging
from pathlib import Path
from utils.drive_utils import create_folder
from utils.config_writer import generate_config_yaml, write_config, upload_config_to_drive
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Costanti
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'service_account.json'
SHARED_DRIVE_ID = '0ADCU0HoCuSCNUk9PVA'
LOCAL_TEMP_CONFIG_PATH = Path("temp_config") / "config.yaml"
CARTELLE_RAW_YAML = Path("config") / "cartelle_raw.yaml"

def init_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def load_folder_structure() -> list[dict]:
    try:
        with open(CARTELLE_RAW_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("root_folders", [])
    except Exception as e:
        logger.error(f"❌ Errore nel parsing di cartelle_raw.yaml: {e}")
        return []

def main():
    print("👤 Pre-onboarding Timmy-KB\n")

    slug = input("🔤 Slug cliente (es. prova): ").strip().lower()
    nome = input("📝 Nome cliente: ").strip()

    config_data = generate_config_yaml(slug, nome)
    write_config(config_data, LOCAL_TEMP_CONFIG_PATH)

    print("\n📝 Contenuto del file di configurazione:")
    print("-------------------------------------------")
    print(LOCAL_TEMP_CONFIG_PATH.read_text(encoding="utf-8"))
    print("-------------------------------------------")

    conferma = input("✅ Confermi il caricamento su Drive? [y/n]: ").strip().lower()

    if conferma != 'y':
        print("❌ Operazione annullata. Pulizia in corso...")
        try:
            LOCAL_TEMP_CONFIG_PATH.unlink()
            logger.info("🗑️  File temporaneo rimosso.")
        except Exception as e:
            logger.warning(f"⚠️  Errore durante la rimozione del file: {e}")
        sys.exit(0)

    logger.info("📡 Avvio upload su Drive...")
    service = init_drive_service()

    # 1. Crea cartella cliente
    folder_id = create_folder(service, name=slug, parent_id=SHARED_DRIVE_ID)

    # 2. Carica file config.yaml
    upload_config_to_drive(service, folder_id, config_data)

    # 3. Crea struttura cartelle da cartelle_raw.yaml
    struttura = load_folder_structure()

    for root in struttura:
        root_name = root.get("name")
        subfolders = root.get("subfolders", [])
        root_id = create_folder(service, name=root_name, parent_id=folder_id)
        logger.info(f"📁 Cartella creata: {root_name} (id: {root_id})")

        for sub in subfolders:
            sub_id = create_folder(service, name=sub, parent_id=root_id)
            logger.info(f"  └─ 📁 Sottocartella: {sub} (id: {sub_id})")

    logger.info("✅ Pre-onboarding completato con successo.")

if __name__ == "__main__":
    main()
