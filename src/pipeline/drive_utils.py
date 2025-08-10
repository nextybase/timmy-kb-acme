import io
import time
from pathlib import Path
from typing import Dict, Any

import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError, PipelineError
from pipeline.constants import GDRIVE_FOLDER_MIME, PDF_MIME_TYPE
from pipeline.context import ClientContext

logger = get_structured_logger("pipeline.drive_utils")

# ---------------------------
# Wrapper API Google Drive con retry
# ---------------------------
def drive_api_call(func, *args, **kwargs):
    for attempt in range(3):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:
                logger.warning(f"[Drive API] Tentativo {attempt + 1} fallito ({e.resp.status}), retry...")
                time.sleep(2 ** attempt)
                continue
            raise
    raise DriveDownloadError("API Google Drive fallita dopo 3 tentativi")

# ---------------------------
# Creazione servizio Drive
# ---------------------------
def get_drive_service(context: ClientContext):
    """Crea un servizio Google Drive autenticato usando variabili da .env."""
    service_account_path = context.env.get("GOOGLE_SERVICE_ACCOUNT")
    if not service_account_path or not Path(service_account_path).exists():
        raise PipelineError("File di service account Google mancante o non trovato. Verifica GOOGLE_SERVICE_ACCOUNT in .env.")

    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

# ---------------------------
# Funzioni di utilità Drive
# ---------------------------
def create_drive_folder(service, name: str, parent_id: str = None) -> str:
    file_metadata = {"name": name, "mimeType": GDRIVE_FOLDER_MIME}
    if parent_id:
        file_metadata["parents"] = [parent_id]

    folder = drive_api_call(service.files().create, body=file_metadata, fields="id", supportsAllDrives=True).execute()
    folder_id = folder.get("id")
    logger.info(f"📂 Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
    return folder_id

def upload_config_to_drive_folder(service, context: ClientContext, folder_id: str):
    """Carica il config.yaml nella cartella Drive indicata."""
    config_path = context.config_path
    if not config_path.exists():
        raise DriveUploadError(f"Config file non trovato: {config_path}")

    file_metadata = {"name": config_path.name, "parents": [folder_id]}
    media = MediaFileUpload(str(config_path), mimetype="application/x-yaml")
    try:
        drive_api_call(
            service.files().create,
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()
        logger.info(f"📤 Config caricato: {config_path} → cartella {folder_id}")
    except Exception as e:
        raise DriveUploadError(f"Errore upload config {config_path}: {e}")

def create_drive_structure_from_yaml(service, yaml_path: Path, parent_id: str) -> Dict[str, str]:
    """Crea su Drive la struttura di cartelle definita in un file YAML."""
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore lettura YAML {yaml_path}: {e}")
        raise PipelineError(e)

    def _create_subfolders(base_parent_id, folders):
        ids = {}
        for folder in folders:
            folder_id = create_drive_folder(service, folder["name"], base_parent_id)
            ids[folder["name"]] = folder_id
            if folder.get("subfolders"):
                ids.update(_create_subfolders(folder_id, folder["subfolders"]))
        return ids

    logger.info(f"📂 Creazione struttura Drive da {yaml_path}")
    mapping = _create_subfolders(parent_id, config.get("root_folders", []))
    logger.info(f"✅ Struttura Drive creata con {len(mapping)} cartelle.")
    return mapping

# ---------------------------
# Download PDF da Drive
# ---------------------------
def download_drive_pdfs_to_local(service, context: ClientContext, drive_folder_id: str, local_path: Path):
    """
    Scarica i file PDF dalla cartella Drive indicata al percorso locale.
    """
    local_path.mkdir(parents=True, exist_ok=True)

    def _download_folder_contents(folder_id: str, current_local_path: Path):
        current_local_path.mkdir(parents=True, exist_ok=True)

        try:
            query = f"'{folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                fields="files(id, name, mimeType)",
                corpora="drive",
                driveId=context.env.get("DRIVE_ID"),  # ⬅️ ora legge da .env
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()

            items = results.get("files", [])
            for item in items:
                name = item["name"]
                mime_type = item["mimeType"]

                if mime_type == PDF_MIME_TYPE:
                    file_id = item["id"]
                    local_file_path = current_local_path / name
                    logger.info(f"⬇️ Scaricamento PDF: {name} → {local_file_path}")

                    request = service.files().get_media(fileId=file_id)
                    fh = io.FileIO(local_file_path, "wb")
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        logger.info(f"   Progresso: {int(status.progress() * 100)}%")
                elif mime_type == GDRIVE_FOLDER_MIME:
                    sub_local_path = current_local_path / name
                    logger.info(f"📁 Entrando nella cartella: {name}")
                    _download_folder_contents(item["id"], sub_local_path)

        except HttpError as error:
            logger.error(f"❌ Errore durante download da Drive: {error}")
            raise DriveDownloadError(error)

    _download_folder_contents(drive_folder_id, local_path)

# ---------------------------
# Creazione struttura locale cliente
# ---------------------------
def create_local_base_structure(context: ClientContext, yaml_path: Path):
    """Crea la struttura locale per un cliente a partire dal file YAML."""
    local_logger = get_structured_logger("preonboarding.structure")

    base_dir = context.output_dir
    (base_dir / "book").mkdir(parents=True, exist_ok=True)
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        local_logger.error(f"❌ Errore nel leggere {yaml_path}: {e}")
        raise PipelineError(e)

    for folder in cfg.get("root_folders", []):
        if folder["name"] == "raw" and folder.get("subfolders"):
            for sub in folder["subfolders"]:
                (raw_dir / sub["name"]).mkdir(parents=True, exist_ok=True)
                local_logger.info(f"📁 Creata cartella locale: {raw_dir / sub['name']}")

    local_logger.info(f"📦 Struttura locale creata in {base_dir}")
    return base_dir
