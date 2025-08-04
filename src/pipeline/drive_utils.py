import io
import mimetypes
import yaml
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError, PipelineError
from pipeline.config_utils import get_config

logger = get_structured_logger("pipeline.drive_utils")
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service(slug: str):
    logger.debug("Inizializzo connessione a Google Drive API.")
    config = get_config(slug)

    if not config.secrets or not getattr(config.secrets, "SERVICE_ACCOUNT_FILE", None):
        logger.error("❌ SERVICE_ACCOUNT_FILE mancante nei secrets!")
        raise PipelineError("SERVICE_ACCOUNT_FILE mancante nei secrets/config!")

    creds = service_account.Credentials.from_service_account_file(
        config.secrets.SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, name: str, parent_id: str) -> str:
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
        logger.info(f"✅ Creata cartella '{name}' (ID: {folder_id}) su Drive (parent: {parent_id})")
        return folder_id
    except Exception as e:
        logger.error(f"❌ Errore nella creazione della cartella '{name}': {e}")
        raise DriveUploadError(f"Errore nella creazione della cartella '{name}': {e}")

def download_drive_pdfs_recursively(service, folder_id: str, raw_dir_path: Path, drive_id: str):
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
                logger.info(f"📥 Scaricato PDF: {local_path}")

            elif mime_type == 'application/vnd.google-apps.folder':
                new_dest = raw_dir_path if name.lower() == 'raw' and raw_dir_path.name.lower() == 'raw' else raw_dir_path / name
                new_dest.mkdir(parents=True, exist_ok=True)
                download_drive_pdfs_recursively(service, file_id, new_dest, drive_id)

    except HttpError as e:
        logger.error(f"❌ Errore nel download ricorsivo: {e}")
        raise DriveDownloadError(f"Errore nel download ricorsivo: {e}")

def download_drive_pdfs_to_local(service, config) -> bool:
    slug = config.slug
    drive_id = config.secrets.DRIVE_ID
    folder_id = getattr(config, "drive_folder_id", None)
    raw_dir_path = config.raw_dir_path

    logger.info(f"📥 Inizio download PDF per il cliente: {slug}")
    if not folder_id:
        logger.error("❌ drive_folder_id mancante in config.")
        raise DriveDownloadError("drive_folder_id mancante in config.")

    download_drive_pdfs_recursively(service, folder_id, raw_dir_path, drive_id)
    logger.info("✅ Download PDF completato.")
    return True

def create_drive_subfolders_from_yaml(service, drive_id: str, parent_folder_id: str, yaml_path: Path) -> bool:
    logger.info(f"📄 Parsing YAML struttura cartelle: {yaml_path}")
    try:
        with open(yaml_path, "r", encoding="utf-8") as file:
            structure = yaml.safe_load(file)

        if not isinstance(structure, dict):
            raise DriveUploadError("YAML non valido: atteso dizionario.")

        def create_nested_folders(parent_id, folders, depth=0):
            for folder in folders:
                name = folder.get("name")
                if not name:
                    logger.warning("⚠️ Cartella senza nome saltata.")
                    continue
                new_folder_id = create_drive_folder(service, name, parent_id)
                logger.info("  " * depth + f"📂 Creata cartella '{name}' (ID: {new_folder_id})")
                subfolders = folder.get("subfolders")
                if isinstance(subfolders, list):
                    create_nested_folders(new_folder_id, subfolders, depth + 1)

        root_folders = structure.get("root_folders", [])
        if not isinstance(root_folders, list):
            raise DriveUploadError("'root_folders' deve essere una lista.")

        logger.info(f"📁 Inizio creazione struttura cartelle nel Drive condiviso ID: {drive_id}")
        create_nested_folders(parent_folder_id, root_folders)
        logger.info("✅ Struttura cartelle creata con successo.")
        return True

    except Exception as e:
        logger.error(f"❌ Errore nel parsing YAML o creazione sottocartelle: {e}")
        raise DriveUploadError(f"Errore nella creazione sottocartelle: {e}")

def find_drive_folder_by_name(service, name: str, drive_id: str = None):
    logger.debug(f"🔎 Ricerca cartella '{name}' in Drive (ID: {drive_id})")
    try:
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
        if drive_id:
            query += f" and '{drive_id}' in parents"
        params = {
            "q": query,
            "spaces": "drive",
            "fields": "files(id, name)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "corpora": "drive" if drive_id else "user"
        }
        if drive_id:
            params["driveId"] = drive_id

        results = service.files().list(**params).execute()
        files = results.get("files", [])
        logger.info(f"🔎 Trovate {len(files)} cartelle con nome '{name}'.")
        return files[0] if files else None

    except Exception as e:
        logger.error(f"❌ Errore nella ricerca della cartella '{name}': {e}")
        raise DriveDownloadError(f"Errore durante la ricerca della cartella '{name}': {e}")

def upload_folder_to_drive_raw(service, raw_dir_path: Path, drive_id: str, drive_raw_folder_id: str):
    def upload_file(file_path: Path, parent_id: str):
        file_metadata = {
            'name': file_path.name,
            'parents': [parent_id]
        }
        mimetype, _ = mimetypes.guess_type(str(file_path))
        media = MediaFileUpload(str(file_path), mimetype=mimetype)
        try:
            service.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True
            ).execute()
            logger.info(f"📤 Caricato file: {file_path.name} (cartella ID: {parent_id})")
        except Exception as e:
            logger.error(f"❌ Errore caricando file {file_path.name}: {e}")

    def find_or_create_drive_folder(service, parent_id: str, folder_name: str) -> str:
        query = (
            f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        results = service.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        if results:
            return results[0]['id']
        folder_metadata = {
            'name': folder_name,
            'parents': [parent_id],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, supportsAllDrives=True, fields='id').execute()
        return folder['id']

    def upload_recursive(local_path: Path, parent_drive_id: str):
        for item in local_path.iterdir():
            if item.is_file():
                upload_file(item, parent_drive_id)
            elif item.is_dir():
                subfolder_id = find_or_create_drive_folder(service, parent_drive_id, item.name)
                upload_recursive(item, subfolder_id)

    upload_recursive(raw_dir_path, drive_raw_folder_id)
    logger.info("✅ Upload ricorsivo cartella raw completato.")

def upload_config_to_drive_folder(service, config_path: Path, drive_folder_id: str):
    query = (
        f"'{drive_folder_id}' in parents and name = '{config_path.name}' and trashed = false"
    )
    results = service.files().list(
        q=query,
        fields='files(id, name)',
        supportsAllDrives=True
    ).execute().get('files', [])

    for f in results:
        try:
            service.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
        except Exception as e:
            logger.warning(f"⚠️ Errore cancellando vecchio config.yaml: {e}")

    file_metadata = {
        'name': config_path.name,
        'parents': [drive_folder_id],
        'mimeType': 'application/x-yaml'
    }
    media = MediaFileUpload(str(config_path), mimetype='application/x-yaml')
    try:
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            supportsAllDrives=True
        ).execute()
        logger.info(f"✅ Caricato config.yaml su Drive, ID: {uploaded.get('id')}")
        return uploaded.get('id')
    except Exception as e:
        logger.error(f"❌ Errore caricando config.yaml su Drive: {e}")
        raise
