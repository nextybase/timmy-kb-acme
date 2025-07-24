import io
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import DriveDownloadError, DriveUploadError
from pipeline.settings import get_settings

logger = get_structured_logger("pipeline.drive_utils")

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """
    Restituisce un oggetto Google Drive API autenticato con service account,
    utilizzando la configurazione centralizzata Settings.
    """
    logger.debug("Inizializzo connessione a Google Drive API.")
    settings = get_settings()
    # Supporta sia google_service_account_json che service_account_file
    service_account_file = (
        getattr(settings, "drive_service_account_file", None)
        or getattr(settings, "google_service_account_json", None)
        or getattr(settings, "service_account_file", None)
    )
    creds = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, name, parent_id):
    """
    Crea una cartella su Google Drive all'interno della cartella padre specificata.
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

def download_drive_pdfs_recursively(service, folder_id, destination, drive_id):
    """
    Scarica tutti i PDF ricorsivamente da una cartella di Drive all'output locale,
    mantenendo la struttura delle sottocartelle, TUTTO dentro destination (=raw/).
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

        files = results.get('files', [])
        for file in files:
            name = file['name']
            file_id = file['id']
            mime_type = file['mimeType']

            if mime_type == 'application/pdf':
                # Scarica il PDF nella cartella corrente (che DEVE essere una sottocartella di raw/)
                local_path = Path(destination) / name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                request = service.files().get_media(fileId=file_id)
                with io.FileIO(local_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                logger.info(f"📥 Scaricato PDF: {local_path}")

            elif mime_type == 'application/vnd.google-apps.folder':
                # Crea la sottocartella locale (se non esiste), sempre dentro raw/
                new_dest = Path(destination) / name
                new_dest.mkdir(parents=True, exist_ok=True)
                # Ricorsione sulla sottocartella
                download_drive_pdfs_recursively(service, file_id, new_dest, drive_id)

    except HttpError as e:
        logger.error(f"❌ Errore nel download ricorsivo: {e}")
        raise DriveDownloadError(f"Errore nel download ricorsivo: {e}")

def download_drive_pdfs_to_local(service, config):
    """
    Scarica tutti i PDF dalla cartella cliente su Drive all'output locale.
    Usa config dict: deve avere slug, drive_id, drive_folder_id, output_path.
    """
    slug = config["slug"]
    drive_id = config["drive_id"]
    folder_id = config.get("drive_folder_id")
    output_path = config["output_path"]
    logger.info(f"📥 Inizio download PDF per il cliente: {slug}")
    if not folder_id:
        logger.error("❌ drive_folder_id mancante in config: impossibile procedere al download.")
        raise DriveDownloadError("drive_folder_id mancante in config: impossibile procedere al download.")
    download_drive_pdfs_recursively(service, folder_id, output_path, drive_id)
    logger.info("✅ Download PDF completato.")
    return True

def create_drive_subfolders_from_yaml(service, drive_id, parent_folder_id, yaml_path):
    """
    Crea ricorsivamente le sottocartelle su Drive secondo la struttura definita nel file YAML.
    """
    import yaml
    logger.info(f"Parsing YAML struttura cartelle: {yaml_path}")

    try:
        with open(yaml_path, "r", encoding="utf-8") as file:
            structure = yaml.safe_load(file)

        if not isinstance(structure, dict):
            logger.error(f"❌ YAML non valido: atteso dizionario, ottenuto {type(structure)}")
            raise DriveUploadError(f"YAML non valido: atteso dizionario, ottenuto {type(structure)}")

        def create_nested_folders(parent_id, folders, depth=0):
            for folder in folders:
                name = folder.get("name")
                if not name:
                    logger.warning("⚠️ Cartella senza nome saltata.")
                    continue

                new_folder_id = create_drive_folder(service, name, parent_id)
                indent = "  " * depth
                logger.info(f"{indent}📂 Creata cartella '{name}' (ID: {new_folder_id})")

                subfolders = folder.get("subfolders")
                if isinstance(subfolders, list) and subfolders:
                    create_nested_folders(new_folder_id, subfolders, depth + 1)

        root_folders = structure.get("root_folders", [])
        if not isinstance(root_folders, list):
            logger.error("❌ 'root_folders' deve essere una lista nel file YAML.")
            raise DriveUploadError("'root_folders' deve essere una lista nel file YAML.")

        logger.info("📁 Inizio creazione struttura cartelle da YAML...")
        create_nested_folders(parent_folder_id, root_folders)
        logger.info("✅ Struttura cartelle creata con successo.")
        return True

    except Exception as e:
        logger.error(f"❌ Errore nella lettura del file YAML o creazione delle sottocartelle: {e}")
        raise DriveUploadError(f"Errore nella creazione delle sottocartelle: {e}")

def find_drive_folder_by_name(service, name, drive_id=None):
    """
    Cerca una cartella su Drive per nome, opzionalmente all'interno di un drive specifico.
    Restituisce il primo match come dict {id, name} oppure None.
    """
    logger.debug(f"Ricerca cartella '{name}' in Drive (ID: {drive_id})")
    try:
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
        if drive_id:
            query += f" and '{drive_id}' in parents"

        params = {
            "q": query,
            "spaces": "drive",
            "fields": "files(id, name)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True
        }

        if drive_id:
            params["corpora"] = "drive"
            params["driveId"] = drive_id
        else:
            params["corpora"] = "user"

        results = service.files().list(**params).execute()
        files = results.get("files", [])
        logger.info(f"Risultati ricerca cartella '{name}': {len(files)} trovate.")
        return files[0] if files else None

    except Exception as e:
        logger.error(f"❌ Errore durante la ricerca della cartella '{name}': {e}")
        raise DriveDownloadError(f"Errore durante la ricerca della cartella '{name}': {e}")

def upload_folder_to_drive_raw(service, local_folder: Path, drive_id: str, drive_raw_folder_id: str):
    """
    Carica ricorsivamente tutti i file e sottocartelle da local_folder nella cartella 'raw' su Drive.
    - service: oggetto Drive API autenticato
    - local_folder: Path locale della cartella da caricare (es: filetest/raw)
    - drive_id: ID del drive di destinazione (usato solo per riferimento)
    - drive_raw_folder_id: ID cartella 'raw' del cliente su Drive (già creata dal pre-onboarding)
    """
    import mimetypes

    def upload_file(file_path, parent_id):
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
            logger.info(f"📤 Caricato file: {file_path.name} (in cartella Drive ID: {parent_id})")
        except Exception as e:
            logger.error(f"❌ Errore caricando file {file_path.name}: {e}")

    def find_or_create_drive_folder(service, parent_id, folder_name):
        query = (
            f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        results = service.files().list(q=query, supportsAllDrives=True).execute().get('files', [])
        if results:
            return results[0]['id']
        # Altrimenti crea la sottocartella
        folder_metadata = {
            'name': folder_name,
            'parents': [parent_id],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, supportsAllDrives=True, fields='id').execute()
        return folder['id']

    def upload_recursive(local_path, parent_drive_id):
        for item in Path(local_path).iterdir():
            if item.is_file():
                upload_file(item, parent_drive_id)
            elif item.is_dir():
                subfolder_id = find_or_create_drive_folder(service, parent_drive_id, item.name)
                upload_recursive(item, subfolder_id)

    # Inizia dalla cartella raw locale e la root 'raw' su Drive
    upload_recursive(local_folder, drive_raw_folder_id)
    logger.info("✅ Upload ricorsivo cartella raw completato.")
