from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import (
    get_drive_service,
    find_drive_folder_by_name,
    create_drive_folder,
    upload_config_to_drive_folder,
    create_drive_subfolders_from_yaml
)
from pipeline.config_utils import write_client_config_file, TimmySecrets
from pipeline.exceptions import PipelineError
from pipeline.utils import is_valid_slug

def main():
    logger = get_structured_logger("pre_onboarding", "logs/pre_onboarding.log")
    logger.info("▶️ Avvio procedura di pre-onboarding NeXT")
    print("▶️ Procedura di pre-onboarding NeXT")

    try:
        secrets = TimmySecrets()
    except Exception as e:
        print(f"❌ Configurazione globale non valida: {e}")
        logger.error(f"❌ Errore configurazione globale: {e}")
        return

    try:
        # --- Input slug ---
        raw_slug = input("🔤 Inserisci lo slug del cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug non valido. Ammessi solo lettere minuscole, numeri, trattini (es: acme-srl).")
            logger.error(f"❌ Slug cliente non valido: '{raw_slug}' -> '{slug}'")
            return
        logger.info(f"🟢 Slug validato e normalizzato: '{slug}'")

        # --- Input nome cliente ---
        cliente_nome = input("🏷️ Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
        if not cliente_nome:
            print("❌ Nome cliente non valido.")
            logger.error("❌ Nome cliente mancante: operazione annullata.")
            return
        logger.debug(f"Nome cliente ricevuto: '{cliente_nome}'")

        # --- Config (prima di chiamare qualunque funzione che usi il config su disco) ---
        drive_id = secrets.DRIVE_ID
        cartelle_yaml_path = "config/cartelle_raw.yaml"
        logger.debug(f"drive_id: {drive_id} | cartelle_yaml_path: {cartelle_yaml_path}")

        # --- Costruzione e scrittura file config PRIMA della connessione a Drive ---
        output_base = f"output/timmy-kb-{slug}"
        raw_dir = f"{output_base}/raw"
        md_output_path = f"{output_base}/book"

        config_data = {
            "slug": slug,
            "cliente_nome": cliente_nome,
            "drive_folder_id": None,   # da aggiornare dopo la creazione su Drive!
            "drive_id": drive_id,
            "output_path": output_base,
            "md_output_path": md_output_path,
            "raw_dir": raw_dir
        }
        config_path = write_client_config_file(config_data, slug)
        logger.info(f"✅ File config.yaml salvato (step preliminare): {config_path}")

        # --- Connessione a Google Drive ---
        service = get_drive_service(slug)
        logger.info("🟢 Connessione a Google Drive riuscita.")

        # --- Check cartella già esistente ---
        folder = find_drive_folder_by_name(service, slug, drive_id=drive_id)
        if folder:
            logger.warning(f"⚠️ Cartella già esistente su Drive: {slug} (ID: {folder['id']})")
            print(f"❌ Esiste già una cartella chiamata '{slug}' (ID: {folder['id']}) su Drive.")
            return

        # --- Crea cartella principale ---
        drive_folder_id = create_drive_folder(service, slug, parent_id=drive_id)
        logger.info(f"✅ Creata cartella '{slug}' (ID: {drive_folder_id})")

        # --- Sottocartelle da YAML ---
        create_drive_subfolders_from_yaml(service, drive_id, drive_folder_id, cartelle_yaml_path)
        logger.info("✅ Struttura sottocartelle creata correttamente.")

        # --- Aggiorna config con drive_folder_id e risalva ---
        config_data["drive_folder_id"] = drive_folder_id
        config_path = write_client_config_file(config_data, slug)
        logger.info(f"✅ File config.yaml aggiornato con drive_folder_id: {config_path}")

        # --- Upload su Drive ---
        upload_config_to_drive_folder(service, config_path, drive_folder_id)
        logger.info("✅ File config.yaml caricato su Google Drive.")

        logger.info(f"🏁 Pre-onboarding completato per: {slug}")
        print(f"✅ Pre-onboarding completato per il cliente: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore bloccante nella pipeline: {e}")
        print(f"❌ Errore bloccante: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore non gestito: {e}", exc_info=True)
        print(f"❌ Errore imprevisto: {e}")
        return

if __name__ == "__main__":
    main()
