import io
import time
from pathlib import Path
from typing import Optional, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError, PipelineError
from pipeline.constants import GDRIVE_FOLDER_MIME, PDF_MIME_TYPE
from pipeline.config_utils import get_settings_for_slug
from pipeline.utils import _validate_path_in_base_dir

logger = get_structured_logger("pipeline.drive_utils")


# ---------------------------
# Wrapper API Google Drive
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
def get_drive_service(settings_instance=None, slug: Optional[str] = None):
    if settings_instance:
        cfg = settings_instance
    elif slug:
        cfg = get_settings_for_slug(slug)
    else:
        raise PipelineError("Impossibile inizializzare Drive service: settings o slug mancanti.")

    creds = service_account.Credentials.from_service_account_file(
        cfg.SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


# ---------------------------
# Funzioni di utilità Drive
# ---------------------------
def create_drive_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    file_metadata = {
        "name": name,
        "mimeType": GDRIVE_FOLDER_MIME
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]

    folder = drive_api_call(
        service.files().create,
        body=file_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()

    folder_id = folder.get("id")
    logger.info(f"📂 Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
    return folder_id


def upload_config_to_drive_folder(service, config_path: Path, folder_id: str, base_dir: Path):
    """
    Carica un file config YAML su una cartella Drive (Shared Drive compatibile).
    """
    _validate_path_in_base_dir(config_path, base_dir)
    file_metadata = {
        "name": config_path.name,
        "parents": [folder_id]
    }
    media = MediaFileUpload(str(config_path), mimetype="application/x-yaml")
    try:
        drive_api_call(
            service.files().create,
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()
        logger.info(f"📤 Config caricata: {config_path} → Drive folder {folder_id}")
    except Exception as e:
        raise DriveUploadError(f"Errore upload config {config_path}: {e}")
