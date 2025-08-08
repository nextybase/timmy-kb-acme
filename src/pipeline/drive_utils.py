import io
import os
from pathlib import Path
from typing import Optional
import yaml

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2 import service_account

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveUploadError

logger = get_structured_logger("pipeline.drive_utils", "logs/timmy-kb-drive-utils.log")

# -------------------------------------------------------------------
# AUTENTICAZIONE GOOGLE DRIVE
# -------------------------------------------------------------------

def get_drive_service(settings):
    creds = service_account.Credentials.from_service_account_file(
        settings.SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


# -------------------------------------------------------------------
# CREAZIONE CARTELLE E UPLOAD
# -------------------------------------------------------------------

def create_drive_folder(service, name: str, parent_id: str) -> str:
    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = service.files().create(
        body=file_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()
    folder_id = folder.get("id")
    logger.info(f"📁 Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
    return folder_id


def find_drive_folder_by_name(service, name: str, parent_id: str, drive_id: str) -> Optional[dict]:
    from googleapiclient.errors import HttpError
    try:
        query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed = false"
        results = service.files().list(
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
            logger.warning(f"⚠️ Parent ID non trovato o non accessibile: {parent_id}. Procedo come se la cartella '{name}' non esistesse.")
            return None
        else:
            logger.error(f"❌ Errore durante la ricerca della cartella '{name}': {e}")
            raise

def upload_config_to_drive_folder(service, config_path: Path, folder_id: str):
    file_metadata = {
        "name": config_path.name,
        "parents": [folder_id]
    }
    media = MediaFileUpload(str(config_path), mimetype="application/x-yaml")
    service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    logger.info(f"⬆️ Config caricato: {config_path} → Drive folder ID {folder_id}")


# -------------------------------------------------------------------
# CREAZIONE SOTTOCARTELLE DA YAML (AGGIORNATA)
# -------------------------------------------------------------------

def create_drive_subfolders_from_yaml(service, parent_id: str, yaml_path: Path):
    """Crea sottocartelle in Drive basate sulla struttura definita in un file YAML (supporto root_folders/subfolders)."""

    def _create_recursive(base_parent_id: str, folders: list):
        """Crea cartelle ricorsivamente in Drive."""
        for folder_def in folders:
            folder_name = folder_def.get("name")
            if not folder_name:
                continue
            # Crea la cartella
            new_folder_id = create_drive_folder(service, folder_name, base_parent_id)
            # Se ci sono sottocartelle, richiamo ricorsivamente
            subfolders = folder_def.get("subfolders", [])
            if subfolders:
                _create_recursive(new_folder_id, subfolders)

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            struttura = yaml.safe_load(f) or {}
        root_folders = struttura.get("root_folders", [])
        if not root_folders:
            logger.warning(f"⚠️ Nessuna cartella trovata in root_folders di {yaml_path}")
            return
        _create_recursive(parent_id, root_folders)
        logger.info(f"✅ Sottocartelle create da YAML: {yaml_path}")
    except Exception as e:
        logger.error(f"❌ Errore creazione sottocartelle da {yaml_path}: {e}", exc_info=True)
        raise DriveUploadError(f"Errore creazione sottocartelle da {yaml_path}: {e}")


# -------------------------------------------------------------------
# DOWNLOAD PDF DA DRIVE
# -------------------------------------------------------------------

def download_drive_pdfs_recursively(service, folder_id: str, local_path: Path, drive_id: str):
    """Scarica tutti i PDF da una cartella Drive (e sottocartelle) mantenendo la struttura."""
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
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
            logger.info(f"⬇️ Scaricato PDF: {file_name} → {local_file_path}")
        elif item["mimeType"] == "application/vnd.google-apps.folder":
            subfolder_path = local_path / item["name"]
            subfolder_path.mkdir(parents=True, exist_ok=True)
            download_drive_pdfs_recursively(service, item["id"], subfolder_path, drive_id)


def download_drive_pdfs_to_local(service, settings, drive_folder_id: str, drive_id: str):
    """Scarica i PDF da Drive in locale mantenendo la struttura."""
    local_path = Path(settings.raw_dir)
    local_path.mkdir(parents=True, exist_ok=True)
    download_drive_pdfs_recursively(service, drive_folder_id, local_path, drive_id)
