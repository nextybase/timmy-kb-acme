"""
drive_utils.py

Utility per l’integrazione con Google Drive nella pipeline Timmy-KB.
Gestisce autenticazione, creazione e ricerca cartelle, download/upload ricorsivo di file PDF,
upload config, generazione struttura da YAML, e funzioni di supporto alla pipeline documentale.
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
from pipeline.config_utils import settings  # <--- settings centralizzato

logger = get_structured_logger("pipeline.drive_utils")
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """
    Inizializza e restituisce una sessione autenticata Google Drive API v3.
    Usa settings.SERVICE_ACCOUNT_FILE come file di credenziali.
    """
    logger.debug("Inizializzo connessione a Google Drive API.")
    if not getattr(settings, "SERVICE_ACCOUNT_FILE", None):
        logger.error("❌ SERVICE_ACCOUNT_FILE mancante nei settings!")
        raise PipelineError("SERVICE_ACCOUNT_FILE mancante nei settings!")
    creds = service_account.Credentials.from_service_account_file(
        settings.SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, name: str, parent_id: str) -> str:
    """
    Crea una nuova cartella su Google Drive all’interno di parent_id.
    """
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
    """
    Scarica ricorsivamente tutti i PDF da una cartella Drive (e sottocartelle),
    salvandoli in raw_dir_path.
    """
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

def download_drive_pdfs_to_local(service, drive_folder_id=None, drive_id=None) -> bool:
    """
    Wrapper che scarica tutti i PDF dalla cartella Drive specificata su settings.RAW_DIR.
    Usa drive_folder_id come cartella radice del cliente.
    """
    if drive_folder_id is None:
        logger.error("❌ drive_folder_id mancante nei settings/config!")
        raise DriveDownloadError("drive_folder_id mancante nei settings/config! Pre-onboarding non completato o config corrotto.")

    # RAW_DIR può essere una property, quindi si può mantenere anche minuscolo se definito come property!
    raw_dir_path = getattr(settings, "RAW_DIR", None)
    if raw_dir_path is None and hasattr(settings, "raw_dir"):
        raw_dir_path = settings.raw_dir

    logger.info(f"📥 Inizio download PDF per la pipeline (drive_folder_id: {drive_folder_id})")

    download_drive_pdfs_recursively(service, drive_folder_id, raw_dir_path, drive_id)
    logger.info("✅ Download PDF completato.")
    return True

def create_drive_subfolders_from_yaml(service, drive_id: str, parent_folder_id: str, yaml_path: Path) -> bool:
    """
    Crea la struttura di sottocartelle in Drive a partire da file YAML (formato {"root_folders": [...]})
    """
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
        logger.info(f"📁 Inizio creazione struttura cartelle nel Drive cliente ID: {drive_id}")
        create_nested_folders(parent_folder_id, root_folders)
        logger.info("✅ Struttura cartelle creata con successo.")
        return True
    except Exception as e:
        logger.error(f"❌ Errore nel parsing YAML o creazione sottocartelle: {e}")
        raise DriveUploadError(f"Errore nella creazione sottocartelle: {e}")

def find_drive_folder_by_name(service, name: str, drive_id: str = None):
    """
    Ricerca una cartella per nome su Google Drive (nella root del Drive specificato).
    """
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

def upload_folder_to_drive_raw(service, raw_dir_path: Path = None, drive_id: str = None, drive_raw_folder_id: str = None):
    """
    Carica ricorsivamente tutti i file dalla cartella RAW_DIR su Drive,
    mantenendo la struttura di sottocartelle.
    Se non passati, usa quelli di settings.
    """
    if raw_dir_path is None:
        raw_dir_path = getattr(settings, "RAW_DIR", None)
        if raw_dir_path is None and hasattr(settings, "raw_dir"):
            raw_dir_path = settings.raw_dir
    if drive_id is None:
        drive_id = getattr(settings, "drive_folder_id", None)
    if drive_raw_folder_id is None:
        drive_raw_folder_id = getattr(settings, "drive_folder_id", None)
    if not drive_raw_folder_id:
        logger.error("❌ drive_folder_id mancante per upload raw!")
        raise DriveUploadError("drive_folder_id mancante nei settings/config.")

    errors = []

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
            logger.exception(f"❌ Errore caricando file {file_path.name}: {e}")
            errors.append((file_path, e))

    def find_or_create_drive_folder(service, parent_id: str, folder_name: str) -> str:
        query = (
            f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        try:
            results = service.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        except Exception as e:
            logger.exception(f"❌ Errore nella ricerca/creazione della sottocartella '{folder_name}': {e}")
            raise DriveUploadError(f"Errore nella ricerca/creazione sottocartella: {e}")

        if results:
            return results[0]['id']
        folder_metadata = {
            'name': folder_name,
            'parents': [parent_id],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        try:
            folder = service.files().create(body=folder_metadata, supportsAllDrives=True, fields='id').execute()
            logger.info(f"📂 Creata sottocartella: {folder_name} (ID: {folder['id']})")
            return folder['id']
        except Exception as e:
            logger.exception(f"❌ Errore creando sottocartella '{folder_name}': {e}")
            raise DriveUploadError(f"Errore creando sottocartella: {e}")

    def upload_recursive(local_path: Path, parent_drive_id: str):
        for item in local_path.iterdir():
            if item.is_file():
                upload_file(item, parent_drive_id)
            elif item.is_dir():
                try:
                    subfolder_id = find_or_create_drive_folder(service, parent_drive_id, item.name)
                    upload_recursive(item, subfolder_id)
                except Exception as e:
                    logger.exception(f"❌ [Ricorsivo] Errore creando/caricando sottocartella {item}: {e}")
                    errors.append((item, e))

    upload_recursive(raw_dir_path, drive_raw_folder_id)
    logger.info("✅ Upload ricorsivo cartella raw completato.")

    if errors:
        error_files = ', '.join(str(f[0]) for f in errors)
        logger.error(f"❌ Upload fallito per i seguenti file/cartelle: {error_files}")
        raise DriveUploadError(f"Upload fallito per i seguenti file/cartelle: {error_files}")

    return True

def upload_config_to_drive_folder(service, config_path: Path, drive_folder_id: str = None):
    """
    Carica config.yaml su Drive, eliminando eventuali versioni precedenti nella cartella.
    Se drive_folder_id non è passato, usa quello di settings.
    """
    if drive_folder_id is None:
        drive_folder_id = getattr(settings, "drive_folder_id", None)
    if not drive_folder_id:
        logger.error("❌ drive_folder_id mancante per upload config!")
        raise DriveUploadError("drive_folder_id mancante nei settings/config.")

    # Elimina eventuali config.yaml già presenti
    query = (
        f"'{drive_folder_id}' in parents and name = '{config_path.name}' and trashed = false"
    )
    try:
        results = service.files().list(
            q=query,
            fields='files(id, name)',
            supportsAllDrives=True
        ).execute().get('files', [])
    except Exception as e:
        logger.warning(f"⚠️ Errore nel check pre-upload config.yaml: {e}")
        results = []
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
