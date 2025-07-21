import os
from pathlib import Path
from dotenv import load_dotenv
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import (
    get_drive_service,
    find_drive_folder_by_name,
    create_drive_folder,
    create_drive_subfolders_from_yaml
)
from pipeline.config_utils import upload_config_to_drive_folder, write_client_config_file

# ▶️ Setup logging e variabili ambiente
load_dotenv()
logger = get_structured_logger("pre_onboarding", "logs/pre_onboarding.log")

def main():
    logger.info("▶️ Avvio procedura di pre-onboarding NeXT")
    print("▶️ Procedura di pre-onboarding NeXT")

    # --- Input slug ---
    raw_slug = input("🔤 Inserisci lo slug del cliente: ").strip().lower()
    logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
    if not raw_slug:
        print("❌ Slug non valido.")
        logger.error("Slug cliente mancante: operazione annullata.")
        return

    # Applica naming rule slug
    slug = raw_slug.replace("_", "-")
    logger.info(f"Slug normalizzato: '{slug}'")

    # --- Input nome cliente ---
    cliente_nome = input("🏷️ Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
    logger.debug(f"Nome cliente da input: '{cliente_nome}'")
    if not cliente_nome:
        print("❌ Nome cliente non valido.")
        logger.error("Nome cliente mancante: operazione annullata.")
        return

    # --- Caricamento variabili ambiente ---
    drive_id = os.getenv("DRIVE_ID")
    cartelle_yaml_path = os.getenv("CARTELLE_RAW_YAML", "config/cartelle_raw.yaml")
    logger.debug(f"drive_id: {drive_id} | cartelle_yaml_path: {cartelle_yaml_path}")
    if not drive_id:
        print("❌ DRIVE_ID non trovato nello .env.")
        logger.error("Variabile DRIVE_ID mancante: impossibile proseguire.")
        return

    # --- Connessione a Google Drive ---
    try:
        service = get_drive_service()
        logger.info("Connessione a Google Drive riuscita.")
    except Exception as e:
        logger.error(f"❌ Errore di connessione a Google Drive: {e}")
        print("❌ Impossibile connettersi a Google Drive.")
        return

    # --- Check cartella esistente ---
    folder = find_drive_folder_by_name(service, slug, drive_id=drive_id)
    if folder:
        logger.warning(f"Cartella già esistente su Drive: {slug} (ID: {folder['id']})")
        print(f"❌ Esiste già una cartella chiamata '{slug}' (ID: {folder['id']}) su Drive.")
        return

    # --- Crea cartella root cliente ---
    try:
        cliente_folder_id = create_drive_folder(service, slug, parent_id=drive_id)
        logger.info(f"✅ Creata cartella '{slug}' (ID: {cliente_folder_id})")
    except Exception as e:
        logger.error(f"❌ Errore nella creazione cartella root: {e}")
        print("❌ Impossibile creare la cartella root su Drive.")
        return

    # --- Crea sottocartelle ---
    try:
        create_drive_subfolders_from_yaml(service, drive_id, cliente_folder_id, cartelle_yaml_path)
        logger.info("✅ Struttura sottocartelle creata correttamente.")
    except Exception as e:
        logger.error(f"❌ Errore nella creazione delle sottocartelle: {e}")
        print("❌ Errore nella creazione delle sottocartelle.")
        return

    # --- Genera e salva config.yaml ---
    config_data = {
        "slug": slug,
        "cliente_nome": cliente_nome,
        "drive_folder_id": cliente_folder_id,
        "drive_id": drive_id,
        "output_path": f"output/timmy-kb-{slug}",
        "md_output_path": f"output/timmy-kb-{slug}/book"
    }
    logger.debug(f"Config data generato: {config_data}")

    local_config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    try:
        write_client_config_file(config_data, local_config_path)
        logger.info(f"✅ File config.yaml salvato localmente: {local_config_path}")
    except Exception as e:
        logger.error(f"❌ Errore nella scrittura locale config.yaml: {e}")
        print("❌ Errore nella scrittura del file di configurazione.")
        return

    # --- Upload config.yaml su Drive ---
    try:
        upload_config_to_drive_folder(service, cliente_folder_id, config_data)
        logger.info("✅ File config.yaml caricato su Google Drive.")
    except Exception as e:
        logger.error(f"❌ Errore nel caricamento su Drive: {e}")
        print("❌ Errore nel caricamento del file su Drive.")
        return

    logger.info(f"✅ Pre-onboarding completato per il cliente: {slug}")
    print(f"✅ Pre-onboarding completato per il cliente: {slug}")

if __name__ == "__main__":
    main()
