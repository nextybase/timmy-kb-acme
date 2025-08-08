"""
pre_onboarding.py

Procedura di pre-onboarding per pipeline NeXT.
Crea la configurazione di progetto e la struttura di cartelle locali e su Google Drive per il cliente specificato.
Valida input e ambiente, genera/configura file, effettua upload su Drive e struttura le sottocartelle secondo YAML.
"""

# Standard library
import sys
from pathlib import Path
import argparse

# Third-party packages
import yaml
from dotenv import load_dotenv

# Local modules
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import (
    get_drive_service,
    find_drive_folder_by_name,
    create_drive_folder,
    upload_config_to_drive_folder,
    create_drive_subfolders_from_yaml,
)
from pipeline.config_utils import write_client_config_file, get_settings_for_slug
from pipeline.exceptions import PipelineError, PreOnboardingValidationError
from pipeline.utils import is_valid_slug, validate_preonboarding_environment

# Carica .env subito dopo gli import di terze parti
load_dotenv()

def preonboarding_main(slug=None, client_name=None, no_interactive=False):
    """
    Orchestrates the Pre-Onboarding phase for a new semantic onboarding process.
    """
    logger = get_structured_logger("pre_onboarding", "logs/timmy-kb-preonboarding.log")
    logger.info("🌤 Procedura di pre-onboarding NeXT")
    try:
        validate_preonboarding_environment()

        # 1. Raccolgli slug
        if not slug:
            if no_interactive:
                logger.error("Slug non fornito in modalità no-interattiva. Uscita.")
                raise PipelineError("Slug non fornito in modalità no-interattiva.")
            slug = input("🌤 Inserisci lo slug del cliente: ").strip().lower()
        slug = slug.replace("_", "-")
        logger.debug(f"Slug ricevuto: '{slug}'")
        if not is_valid_slug(slug):
            logger.error(f"Slug non valido: '{slug}'. Ammessi solo lettere, numeri, trattini (es: acme-srl).")
            raise PipelineError(f"Slug non valido: '{slug}'")

        # 2. Raccogli client_name
        if not client_name:
            if no_interactive:
                logger.error("Nome cliente non fornito in modalità no-interattiva. Uscita.")
                raise PipelineError("Nome cliente non fornito in modalità no-interattiva.")
            client_name = input("👤 Inserisci il nome completo del cliente (es. Acme S.r.l.): ").strip()
        if not client_name:
            logger.error("Nome cliente mancante.")
            raise PipelineError("Nome cliente mancante.")

        # 3. Carica template config.yaml base
        base_config_yaml = Path("config/config.yaml")
        if not base_config_yaml.exists():
            logger.error("File config/config.yaml mancante.")
            raise PipelineError("File config/config.yaml mancante.")

        with open(base_config_yaml, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)

        # 4. Applica parametri cliente su config dict
        config_dict["slug"] = slug
        config_dict["output_dir"] = config_dict.get("output_dir_template", "output/timmy-kb-{slug}").format(slug=slug)
        config_dict["raw_dir"] = config_dict.get("raw_dir_template", "output/timmy-kb-{slug}/raw").format(slug=slug)
        config_dict["md_output_path"] = str(Path(config_dict["output_dir"]) / "book")
        config_dict["client_name"] = client_name

        # 5. Scrivi config cliente YAML su output
        config_path = write_client_config_file(config_dict, slug)
        logger.info(f"Config YAML scritto in: {config_path}")

        # 6. Crea cartelle locali se non esistono
        output_dir = Path(config_dict["output_dir"])
        raw_dir = Path(config_dict["raw_dir"])
        md_dir = Path(config_dict["md_output_path"])
        for folder in [output_dir, raw_dir, md_dir]:
            folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Cartella creata o già esistente: {folder}")

        # 7. Crea settings per lo slug
        settings = get_settings_for_slug(slug)

        # 8. Google Drive setup: crea cartella cliente su Drive se non esiste
        service = get_drive_service(settings)
        parent_id = settings.DRIVE_ID
        drive_folder = find_drive_folder_by_name(service, slug, parent_id, settings.DRIVE_ID)
        if not drive_folder:
            drive_folder_id = create_drive_folder(service, slug, parent_id)
            logger.info(f"📂 Cartella Drive creata: {drive_folder_id}")
        else:
            drive_folder_id = drive_folder['id']
            logger.info(f"📂 Cartella Drive già esistente: {drive_folder_id}")

        # 🔹 CREA cartella RAW sotto la cartella cliente e salva il suo ID
        raw_drive_folder_id = create_drive_folder(service, "raw", drive_folder_id)
        logger.info(f"📂 Cartella 'raw' creata su Drive (ID: {raw_drive_folder_id})")

        # 9. Carica config su Drive
        upload_config_to_drive_folder(service, config_path, drive_folder_id)
        logger.info("📤 Config caricata su Drive.")

        # 10. Aggiorna config con drive_folder_id e raw_folder_id locale
        config_dict["drive_folder_id"] = drive_folder_id
        config_dict["raw_folder_id"] = raw_drive_folder_id
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_dict, f, allow_unicode=True)
        logger.info(f"📝 Aggiornato config con drive_folder_id: {drive_folder_id} e raw_folder_id: {raw_drive_folder_id}")
        logger.debug(f"Contenuto finale config.yaml:\n{yaml.dump(config_dict, allow_unicode=True)}")

        # 11. Crea sottocartelle su Drive da YAML (se presente)
        yaml_path = Path("config/cartelle_raw.yaml")
        if not yaml_path.exists():
            logger.error(f"File YAML struttura cartelle mancante: {yaml_path}")
        else:
            try:
                create_drive_subfolders_from_yaml(service, drive_folder_id, yaml_path)
                logger.info("📂 Struttura cartelle Drive creata da YAML.")
            except Exception as e:
                logger.error(f"Errore creazione struttura cartelle da YAML: {e}")

        logger.info(f"✅ Pre-onboarding completato per: {slug}")

    except PreOnboardingValidationError as e:
        logger.error(f"❌ Errore validazione pre-onboarding: {e}")
        sys.exit(1)
    except PipelineError as e:
        logger.error(f"❌ Errore pipeline: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Procedura di pre-onboarding NeXT (config + setup cartelle)",
        epilog="Esempio: python pre_onboarding.py --slug dummy --client-name 'Dummy Corp' --no-interactive"
    )
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--client-name", type=str, help="Nome completo cliente")
    parser.add_argument("--no-interactive", action="store_true", help="Disabilita input interattivo (solo pipeline/CI)")

    args = parser.parse_args()
    preonboarding_main(
        slug=args.slug,
        client_name=args.client_name,
        no_interactive=args.no_interactive
    )
