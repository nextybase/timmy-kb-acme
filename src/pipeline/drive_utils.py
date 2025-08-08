"""
drive_utils.py

Utility per l'integrazione con Google Drive nella pipeline Timmy-KB.
Funzioni di autenticazione, creazione cartelle, upload/download ricorsivo di file PDF,
upload config, generazione struttura da YAML e funzioni di supporto alla pipeline documentale.

⚠️ NOTA: In questo modulo la connessione a Google Drive è OBBLIGATORIA.
Non sono previsti fallback locali: se DRIVE_ID o credenziali mancano, la pipeline solleva eccezioni bloccanti.
"""

from pathlib import Path
import io
import mimetypes
import yaml
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError, PipelineError

logger = get_structured_logger("pipeline.drive_utils")
SCOPES = ['https://www.googleapis.com/auth/drive']


def get_drive_service(settings):
    """Inizializza e restituisce una sessione autenticata Google Drive API v3."""
    logger.debug("Inizializzo connessione a Google Drive API.")
    if not getattr(settings, "SERVICE_ACCOUNT_FILE", None):
        logger.error("❌ SERVICE_ACCOUNT_FILE mancante nei settings! (Variabile .env obbligatoria in MAIUSCOLO)")
        raise PipelineError("SERVICE_ACCOUNT_FILE mancante nei settings!")
    try:
        creds = service_account.Credentials.from_service_account_file(
            settings.SERVICE_ACCOUNT_FILE,
            scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ Errore creazione servizio Drive: {e}", exc_info=True)
        raise PipelineError(f"Errore creazione servizio Drive: {e}")


def create_drive_folder(service, name: str, parent_id: str) -> str:
    """Crea una nuova cartella su Google Drive all'interno di parent_id."""
    folder_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    try:
        folder = service.files().create(
            body=folder_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        folder_id = folder.get('id')
        logger.info(f"📁 Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
        return folder_id
    except Exception as e:
        logger.error(f"❌ Errore creazione cartella '{name}': {e}", exc_info=True)
        raise DriveUploadError(f"Errore creazione cartella '{name}': {e}")


def download_drive_pdfs_recursively(service, folder_id: str, raw_dir_path: Path, drive_id: str):
    """Scarica ricorsivamente tutti i PDF da una cartella Drive, salvandoli in raw_dir_path."""
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='drive',
            driveId=drive_id
        ).execute()
        for file in results.get('files', []):
            name = file['name']
            file_id = file['id']
            mime_type = file['mimeType']
            if mime_type == 'application/pdf':
                local_path = raw_dir_path / name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                request = service.files().get_media(fileId=file_id)
                with io.FileIO(local_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                logger.info(f"⬇️ Scaricato PDF: {local_path}")
            elif mime_type == 'application/vnd.google-apps.folder':
                new_dest = raw_dir_path / name
                new_dest.mkdir(parents=True, exist_ok=True)
                download_drive_pdfs_recursively(service, file_id, new_dest, drive_id)
    except HttpError as e:
        logger.error(f"❌ Errore download ricorsivo da Drive: {e}", exc_info=True)
        raise DriveDownloadError(f"Errore download ricorsivo da Drive: {e}")


def download_drive_pdfs_to_local(service, settings, drive_folder_id=None, drive_id=None) -> bool:
    """Scarica tutti i PDF dalla cartella Drive specificata in settings.raw_dir."""
    if drive_folder_id is None:
        logger.error("❌ drive_folder_id mancante nei settings/config! (YAML minuscolo)")
        raise DriveDownloadError("drive_folder_id mancante nei settings/config!")
    raw_dir_path = settings.raw_dir
    logger.info(f"⬇️ Avvio download PDF da Drive (drive_folder_id: {drive_folder_id})")
    download_drive_pdfs_recursively(service, drive_folder_id, raw_dir_path, drive_id)
    logger.info("✅ Download PDF completato.")
    return True


def create_drive_subfolders_from_yaml(service, parent_id: str, yaml_path: Path):
    """Crea sottocartelle in Drive basate sulla struttura definita in un file YAML."""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            structure = yaml.safe_load(f) or {}
        for folder_name in structure.get('folders', []):
            create_drive_folder(service, folder_name, parent_id)
        logger.info(f"✅ Sottocartelle create da YAML: {yaml_path}")
    except Exception as e:
        logger.error(f"❌ Errore creazione sottocartelle da {yaml_path}: {e}", exc_info=True)
        raise DriveUploadError(f"Errore creazione sottocartelle da {yaml_path}: {e}")


def find_drive_folder_by_name(service, name: str, parent_id: str, drive_id: str) -> str:
    """Trova l'ID di una cartella su Drive dato il nome e il parent_id."""
    try:
        query = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='drive',
            driveId=drive_id
        ).execute()
        files = results.get('files', [])
        if files:
            folder_id = files[0]['id']
            logger.info(f"📂 Cartella trovata '{name}' (ID: {folder_id}) in parent {parent_id}")
            return folder_id
        logger.warning(f"⚠️ Cartella '{name}' non trovata in parent {parent_id}")
        return None
    except HttpError as e:
        logger.error(f"❌ Errore ricerca cartella '{name}': {e}", exc_info=True)
        raise PipelineError(f"Errore ricerca cartella '{name}': {e}")


def upload_folder_to_drive_raw(service, folder_path: Path, drive_folder_id: str, drive_id: str):
    """Carica ricorsivamente una cartella locale su Drive."""
    if not folder_path.exists():
        logger.error(f"❌ Cartella locale inesistente: {folder_path}")
        raise DriveUploadError(f"Cartella locale inesistente: {folder_path}")
    try:
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                mime_type, _ = mimetypes.guess_type(file_path)
                media = MediaFileUpload(str(file_path), mimetype=mime_type or 'application/octet-stream')
                service.files().create(
                    body={'name': file_path.name, 'parents': [drive_folder_id]},
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
                logger.info(f"⬆️ Caricato file: {file_path} → Drive folder ID {drive_folder_id}")
    except HttpError as e:
        logger.error(f"❌ Errore upload cartella {folder_path}: {e}", exc_info=True)
        raise DriveUploadError(f"Errore upload cartella {folder_path}: {e}")


def upload_config_to_drive_folder(service, config_path: Path, drive_folder_id: str):
    """Carica un file di configurazione nella cartella Drive indicata."""
    if not config_path.exists():
        logger.error(f"❌ File di configurazione inesistente: {config_path}")
        raise DriveUploadError(f"File di configurazione inesistente: {config_path}")
    try:
        media = MediaFileUpload(str(config_path), mimetype='application/x-yaml')
        service.files().create(
            body={'name': config_path.name, 'parents': [drive_folder_id]},
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        logger.info(f"⬆️ Config caricato: {config_path} → Drive folder ID {drive_folder_id}")
    except HttpError as e:
        logger.error(f"❌ Errore upload config {config_path}: {e}", exc_info=True)
        raise DriveUploadError(f"Errore upload config {config_path}: {e}")
