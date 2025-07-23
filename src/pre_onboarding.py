import os
import re
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
from pipeline.exceptions import PipelineError

# ▶️ Setup logging e variabili ambiente
load_dotenv()
logger = get_structured_logger("pre_onboarding", "logs/pre_onboarding.log")

# --- Slug validation utility ---
def is_valid_slug(slug: str) -> bool:
    """
    Verifica che lo slug sia conforme a [a-z0-9-], senza caratteri strani o path traversal.
    """
    if not slug:
        return False
    return re.fullmatch(r"[a-z0-9-]+", slug) is not None

def main():
    logger.info("▶️ Avvio procedura di pre-onboarding NeXT")
    print("▶️ Procedura di pre-onboarding NeXT")

    try:
        # --- Input slug ---
        raw_slug = input("🔤 Inserisci lo slug del cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")

        # --- Validazione robusta dello slug ---
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug non valido. Ammessi solo lettere minuscole, numeri, trattini (es: acme-srl).")
            logger.error(f"❌ Slug cliente non valido: '{raw_slug}' -> '{slug}'")
            return
        logger.info(f"🟢 Slug validato e normalizzato: '{slug}'")

        # --- Input nome cliente ---
        cliente_nome = input("🏷️ Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
        logger.debug(f"Nome cliente da input: '{cliente_nome}'")
        if not cliente_nome:
            print("❌ Nome cliente non valido.")
            logger.error("❌ Nome cliente mancante: operazione annullata.")
            return

        # --- Caricamento variabili ambiente ---
        drive_id = os.getenv("DRIVE_ID")
        cartelle_yaml_path = os.getenv("CARTELLE_RAW_YAML", "config/cartelle_raw.yaml")
        logger.debug(f"drive_id: {drive_id} | cartelle_yaml_path: {cartelle_yaml_path}")
        if not drive_id:
            print("❌ DRIVE_ID non trovato nello .env.")
            logger.error("❌ Variabile DRIVE_ID mancante: impossibile proseguire.")
            return

        # --- Connessione a Google Drive ---
        service = get_drive_service()
        logger.info("🟢 Connessione a Google Drive riuscita.")

        # --- Check cartella esistente ---
        folder = find_drive_folder_by_name(service, slug, drive_id=drive_id)
        if folder:
            logger.warning(f"⚠️ Cartella già esistente su Drive: {slug} (ID: {folder['id']})")
            print(f"❌ Esiste già una cartella chiamata '{slug}' (ID: {folder['id']}) su Drive.")
            return

        # --- Crea cartella root cliente ---
        drive_folder_id = create_drive_folder(service, slug, parent_id=drive_id)
        logger.info(f"✅ Creata cartella '{slug}' (ID: {drive_folder_id})")

        # --- Crea sottocartelle ---
        create_drive_subfolders_from_yaml(service, drive_id, drive_folder_id, cartelle_yaml_path)
        logger.info("✅ Struttura sottocartelle creata correttamente.")

        # --- Genera e salva config.yaml ---
        config_data = {
            "slug": slug,
            "cliente_nome": cliente_nome,
            "drive_folder_id": drive_folder_id,
            "drive_id": drive_id,
            "output_path": f"output/timmy-kb-{slug}",
            "md_output_path": f"output/timmy-kb-{slug}/book"
        }
        logger.debug(f"Config data generato: {config_data}")

        local_config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
        write_client_config_file(config_data, local_config_path)
        logger.info(f"✅ File config.yaml salvato localmente: {local_config_path}")

        # --- Upload config.yaml su Drive ---
        upload_config_to_drive_folder(service, drive_folder_id, config_data)
        logger.info("✅ File config.yaml caricato su Google Drive.")

        logger.info(f"🏁 Pre-onboarding completato per il cliente: {slug}")
        print(f"✅ Pre-onboarding completato per il cliente: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore bloccante nella pipeline: {e}")
        print(f"❌ Errore bloccante: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore non gestito: {e}")
        print(f"❌ Errore imprevisto: {e}")
        return

if __name__ == "__main__":
    main()
