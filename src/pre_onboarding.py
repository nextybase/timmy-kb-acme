import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from utils.logger_utils import get_logger
from utils.drive_utils import (
    get_drive_service,
    find_folder_by_name,
    create_folder,
    create_subfolders_from_yaml
)
from utils.config_writer import upload_config_to_drive, write_config

# ▶️ Logging e variabili
load_dotenv()
logger = get_logger("pre_onboarding", "logs/pre_onboarding.log")

def main():
    print("▶️ Procedura di pre-onboarding NeXT")
    raw_slug = input("🔤 Inserisci lo slug del cliente: ").strip().lower()
    if not raw_slug:
        print("❌ Slug non valido.")
        return

    slug = raw_slug.replace("_", "-")  # ✅ Standard naming
    cliente_nome = input("🏷️ Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
    if not cliente_nome:
        print("❌ Nome cliente non valido.")
        return

    drive_id = os.getenv("DRIVE_ID")
    cartelle_yaml_path = os.getenv("CARTELLE_RAW_YAML", "config/cartelle_raw.yaml")
    if not drive_id:
        print("❌ DRIVE_ID non trovato nello .env.")
        return

    # 📡 Connessione a Drive
    service = get_drive_service()

    # ❌ Blocca se cartella già esistente
    folder = find_folder_by_name(service, slug, drive_id=drive_id)
    if folder:
        print(f"❌ Esiste già una cartella chiamata '{slug}' (ID: {folder['id']}) su Drive.")
        return

    # 📁 Crea cartella principale
    cliente_folder_id = create_folder(service, slug, parent_id=drive_id)
    logger.info(f"✅ Creata cartella '{slug}' (ID: {cliente_folder_id})")

    # 📂 Crea sottocartelle
    try:
        create_subfolders_from_yaml(service, drive_id, cliente_folder_id, cartelle_yaml_path)
    except Exception as e:
        logger.error(f"❌ Errore nella creazione delle sottocartelle: {e}")
        return

    # 📦 Generazione e salvataggio config.yaml
    config_data = {
        "slug": slug,
        "cliente_nome": cliente_nome,
        "drive_folder_id": cliente_folder_id,
        "drive_id": drive_id,
        "output_path": f"output/timmy-kb-{slug}",
        "md_output_path": f"output/timmy-kb-{slug}/book"
    }

    local_config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    write_config(config_data, local_config_path)

    try:
        upload_config_to_drive(service, cliente_folder_id, config_data)
    except Exception as e:
        logger.error(f"❌ Errore nel caricamento su Drive: {e}")
        return

    print(f"✅ Pre-onboarding completato per il cliente: {slug}")

if __name__ == "__main__":
    main()
