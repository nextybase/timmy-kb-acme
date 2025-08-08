import io
import os
import time
from pathlib import Path
from typing import Optional
import shutil
import yaml

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError
from pipeline.constants import OUTPUT_DIR_NAME
from pipeline.config_utils import get_settings_for_slug

logger = get_structured_logger("pipeline.drive_utils")


# -------------------------------
# WRAPPER API CON RETRY E LOGGING
# -------------------------------

def drive_api_call(func, *args, **kwargs):
    """
    Esegue una chiamata API Google Drive con retry/backoff su errori temporanei.
    """
    for attempt in range(3):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:
                logger.warning(f"[Drive API] Tentativo {attempt+1} fallito, retry...")
                time.sleep(2 ** attempt)
                continue
            raise
    raise DriveDownloadError("API Google Drive fallita dopo 3 tentativi")


# -------------------------------
# CREAZIONE SERVIZIO
# -------------------------------

def get_drive_service(settings=None):
    settings = settings or get_settings_for_slug()
    creds = service_account.Credentials.from_service_account_file(
        settings.SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


# -------------------------------
# FUNZIONI ORIGINALI + INTEGRAZIONI
# -------------------------------

def create_drive_folder(service, name: str, parent_id: str) -> str:
    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = drive_api_call(
        service.files().create,
        body=file_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()
    folder_id = folder.get("id")
    logger.info(f"📁 Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
    return folder_id


def find_drive_folder_by_name(service, name: str, parent_id: str, drive_id: str) -> Optional[dict]:
    try:
        query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed = false"
        results = drive_api_call(
            service.files().list,
            q=query,
            spaces="drive",
            fields="files(id, name)",
            corpora="drive",
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True
        ).execute()
        files = results.get("files", [])
        if not files:
            logger.warning(f"⚠️ Cartella '{name}' non trovata in parent {parent_id}")
            return None
        return files[0]
    except HttpError as e:
        if e.resp.status == 404:
            logger.warning(f"⚠️ Parent ID non trovato o non accessibile: {parent_id}")
            return None
        logger.error(f"❌ Errore nella ricerca della cartella '{name}': {e}")
        raise


def upload_config_to_drive_folder(service, config_path: Path, folder_id: str):
    file_metadata = {
        "name": config_path.name,
        "parents": [folder_id]
    }
    media = MediaFileUpload(str(config_path), mimetype="application/x-yaml")
    drive_api_call(
        service.files().create,
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    logger.info(f"📤 Config caricata: {config_path} ➡️ Drive folder ID {folder_id}")


def download_drive_pdfs_recursively(service, folder_id: str, local_path: Path, drive_id: str):
    """
    Scarica tutti i PDF da una cartella Drive e sottocartelle mantenendo la struttura.
    """
    query = f"'{folder_id}' in parents and trashed = false"
    results = drive_api_call(
        service.files().list,
        q=query,
        spaces="drive",
        fields="files(id, name, mimeType)",
        corpora="drive",
        driveId=drive_id,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()

    items = results.get("files", [])
    for item in items:
        if item["mimeType"] == "application/pdf":
            file_id = item["id"]
            file_name = item["name"]
            local_file_path = local_path / file_name
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(local_file_path, "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            logger.info(f"📥 Scaricato PDF: {file_name} ➡️ {local_file_path}")

        elif item["mimeType"] == "application/vnd.google-apps.folder":
            subfolder_path = local_path / item["name"]
            subfolder_path.mkdir(parents=True, exist_ok=True)
            download_drive_pdfs_recursively(service, item["id"], subfolder_path, drive_id)


def download_drive_pdfs_to_local(service, settings, drive_folder_id: str, drive_id: str):
    """
    Scarica i PDF da Drive in locale, mantenendo la struttura.
    """
    local_path = settings.raw_dir
    local_path.mkdir(parents=True, exist_ok=True)
    download_drive_pdfs_recursively(service, drive_folder_id, local_path, drive_id)
