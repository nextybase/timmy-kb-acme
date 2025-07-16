import os
import sys
import logging
import yaml
import tempfile
from pathlib import Path
from typing import Optional, Dict
from pydantic import BaseModel, Field, ValidationError

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'service_account.json'
SHARED_DRIVE_ID = os.getenv("DRIVE_ID", "0ADCU0HoCuSCNUk9PVA")


# Pydantic model for config validation
class ConfigModel(BaseModel):
    cliente_id: str
    drive_input_path: Optional[str] = None
    md_output_path: Optional[str] = None
    github_repo: Optional[str] = None
    github_branch: Optional[str] = "main"
    gitbook_space: Optional[str] = None

def download_config_from_drive(cliente_id: str, local_path: Path) -> bool:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    # Locate client folder
    query = (
        f"'{SHARED_DRIVE_ID}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and name='{cliente_id}'"
    )
    results = service.files().list(
        q=query,
        spaces='drive',
        corpora='drive',
        driveId=SHARED_DRIVE_ID,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields="files(id, name)"
    ).execute()

    folders = results.get('files', [])
    if not folders:
        logger.error(f"❌ Cartella cliente '{cliente_id}' non trovata nel Drive condiviso.")
        return False

    folder_id = folders[0]['id']
    query_file = f"'{folder_id}' in parents and name='config.yaml'"
    file_results = service.files().list(
        q=query_file,
        spaces='drive',
        corpora='allDrives',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields="files(id, name)"
    ).execute()

    files = file_results.get('files', [])
    if not files:
        logger.error("❌ File config.yaml non trovato nella cartella del cliente.")
        return False

    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(local_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    logger.info(f"⬇️  Config.yaml scaricato in: {local_path}")
    return True


def load_config(config_path: Path | str = None, overrides: Optional[Dict] = None) -> dict:
    path = Path(config_path or os.getenv("CONFIG_PATH", "config/config.yaml")).resolve()
    if not path.is_file():
        logger.fatal(f"❌ File di configurazione non trovato: {path}")
        sys.exit(1)

    try:
        raw_cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        logger.fatal(f"❌ Errore di parsing YAML: {e}")
        sys.exit(1)

    # Applica override se presenti
    if overrides:
        raw_cfg.update(overrides)

    try:
        cfg_model = ConfigModel(**raw_cfg)
    except ValidationError as e:
        logger.fatal(f"❌ Errore di validazione config.yaml:\n{e}")
        sys.exit(1)

    cliente_id = cfg_model.cliente_id

    # Percorsi di default
    default_drive = Path("G:/Drive condivisi/Nexty Docs") / cliente_id / "raw"
    drive_input_path = cfg_model.drive_input_path or default_drive
    md_output_path = cfg_model.md_output_path or (Path("output") / f"timmy_kb_{cliente_id}")

    config = {
        "cliente_id": cliente_id,
        "drive_input_path": str(Path(drive_input_path).resolve()),
        "md_output_path": str(Path(md_output_path).resolve()),
        "github_repo": cfg_model.github_repo or f"nextybase/timmy-kb-{cliente_id}",
        "github_branch": cfg_model.github_branch,
        "gitbook_space": cfg_model.gitbook_space or f"Timmy-KB-{cliente_id}",
    }

    logger.info(f"✅ Config caricato per cliente: {cliente_id}")
    return config


def load_config_from_drive(cliente_id: str, overrides: Optional[Dict] = None) -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"config_{cliente_id}.yaml"
    success = download_config_from_drive(cliente_id, temp_path)
    if not success:
        sys.exit(1)
    return load_config(temp_path, overrides=overrides)
