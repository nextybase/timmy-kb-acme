import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from pipeline.drive_utils import (
    get_drive_service,
    download_drive_pdfs_to_local,
    create_drive_subfolders_from_yaml,
    find_drive_folder_by_name,
    upload_config_to_drive_folder,
)
from pipeline.config_utils import get_config
from pipeline.logging_utils import get_structured_logger

SLUG = "dummy"
OUTPUT_BASE = Path(f"output/timmy-kb-{SLUG}")
RAW_DIR = OUTPUT_BASE / "raw"
BOOK_DIR = OUTPUT_BASE / "book"
YAML_STRUCTURE_PATH = Path("config/cartelle_raw.yaml")

logger = get_structured_logger("test_drive_utils")

def test_drive_service_connection():
    config = get_config(SLUG)
    assert config.secrets.SERVICE_ACCOUNT_FILE, "SERVICE_ACCOUNT_FILE mancante nella config."

    try:
        service = get_drive_service(SLUG)
        assert service is not None, "Impossibile creare il servizio Drive."
        logger.info("✅ Connessione a Google Drive API riuscita.")
    except Exception as e:
        pytest.fail(f"❌ Errore durante la connessione al servizio Drive: {e}")

def test_download_pdfs():
    service = get_drive_service(SLUG)
    config = get_config(SLUG)

    try:
        result = download_drive_pdfs_to_local(service, config)
        assert result is True
        assert any(RAW_DIR.rglob("*.pdf")), "❌ Nessun PDF scaricato nella cartella RAW."
        logger.info("✅ Download PDF da Drive riuscito.")
    except Exception as e:
        pytest.fail(f"❌ Errore durante il download dei PDF: {e}")

def test_create_structure_from_yaml():
    service = get_drive_service(SLUG)
    config = get_config(SLUG)

    try:
        success = create_drive_subfolders_from_yaml(
            service,
            drive_id=config.secrets.DRIVE_ID,
            parent_folder_id=config.drive_folder_id,
            yaml_path=YAML_STRUCTURE_PATH,
        )
        assert success is True
        logger.info("✅ Struttura cartelle creata correttamente da YAML.")
    except Exception as e:
        pytest.fail(f"❌ Errore nella creazione struttura Drive da YAML: {e}")

def test_find_folder():
    service = get_drive_service(SLUG)
    config = get_config(SLUG)

    try:
        # ✅ Cerchiamo la cartella senza forzare il drive_id, in modo che cerchi ovunque visibile
        folder = find_drive_folder_by_name(service, name="raw")
        assert folder, "❌ Cartella 'raw' non trovata."
        logger.info(f"✅ Cartella trovata: {folder['name']} (ID: {folder['id']})")
    except Exception as e:
        pytest.fail(f"❌ Errore nella ricerca della cartella: {e}")

def test_upload_config():
    service = get_drive_service(SLUG)
    config = get_config(SLUG)
    config_path = OUTPUT_BASE / "config" / "config.yaml"

    logger.debug(f"🔍 DEBUG: config_path = {config_path}")
    logger.debug(f"🔍 DEBUG: drive_folder_id = {config.drive_folder_id}")

    assert config_path.exists(), f"❌ Il file {config_path} non esiste."

    try:
        config_id = upload_config_to_drive_folder(
            service,
            config_path=config_path,
            drive_folder_id=config.drive_folder_id,
        )
        assert config_id, "❌ Upload del file config.yaml fallito."
        logger.info(f"✅ Config.yaml caricato con ID: {config_id}")
    except Exception as e:
        pytest.fail(f"❌ Errore durante l'upload del config.yaml: {e}")
