from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import (
    get_drive_service,
    find_drive_folder_by_name,
    create_drive_folder,
    upload_config_to_drive_folder,
    create_drive_subfolders_from_yaml
)
from pipeline.config_utils import write_client_config_file, get_config
from pipeline.exceptions import PipelineError
from pipeline.utils import is_valid_slug

def main():
    logger = get_structured_logger("pre_onboarding", "logs/pre_onboarding.log")
    logger.info("▶️ Procedura di pre-onboarding NeXT")
    print("▶️ Procedura di pre-onboarding NeXT")

    try:
        # Step 1: Raccolta dati utente
        raw_slug = input("🔤 Inserisci lo slug del cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug non valido. Ammessi solo lettere, numeri, trattini (es: acme-srl).")
            logger.error(f"Slug non valido: '{slug}'")
            return

        client_name = input("👤 Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
        if not client_name:
            print("❌ Nome cliente non valido.")
            logger.error("Nome cliente mancante.")
            return

        # Step 2: Generazione path/config
        # Carica la config di progetto (template) dalla YAML globale
        # NB: Qui potresti anche fare un merge con un template, se serve
        base_config_yaml = Path("config/config.yaml")
        if not base_config_yaml.exists():
            print("❌ File config/config.yaml mancante.")
            logger.error("File config/config.yaml mancante.")
            return

        with open(base_config_yaml, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)

        # Risolvi i template path con lo slug
        config_dict["slug"] = slug
        config_dict["output_dir"] = config_dict.get("output_dir_template", "output/timmy-kb-{slug}").format(slug=slug)
        config_dict["raw_dir"] = config_dict.get("raw_dir_template", "output/timmy-kb-{slug}/raw").format(slug=slug)
        config_dict["md_output_path"] = str(Path(config_dict["output_dir"]) / "book")
        config_dict["client_name"] = client_name

        # Step 3: Scrittura config.yaml cliente
        config_path = write_client_config_file(config_dict, slug)
        logger.info(f"Config YAML scritto in: {config_path}")

        # Step 4: Crea struttura di cartelle output
        output_dir = Path(config_dict["output_dir"])
        raw_dir = Path(config_dict["raw_dir"])
        md_dir = Path(config_dict["md_output_path"])
        for folder in [output_dir, raw_dir, md_dir]:
            folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cartella creata/già esistente: {folder}")

        # Step 5: Inizializza Google Drive e sottocartelle
        service = get_drive_service(slug)
        drive_folder = find_drive_folder_by_name(service, slug)
        if not drive_folder:
            drive_folder_id = create_drive_folder(service, slug)
            logger.info(f"Cartella Drive creata: {drive_folder_id}")
        else:
            drive_folder_id = drive_folder['id']
            logger.info(f"Cartella Drive già esistente: {drive_folder_id}")

        # Upload config su Drive
        upload_config_to_drive_folder(service, config_path, drive_folder_id)
        logger.info("Config caricata su Drive.")

        print(f"✅ Pre-onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore pipeline: {e}")
        print(f"❌ Errore pipeline: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        print(f"❌ Errore imprevisto: {e}")
        return

if __name__ == "__main__":
    main()
