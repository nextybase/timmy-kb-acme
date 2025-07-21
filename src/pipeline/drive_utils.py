# src/pipeline/drive_utils.py

import os
import io
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.drive_utils")

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")


def get_drive_service():
    """
    Restituisce un oggetto Google Drive API autenticato con service account.
    """
    logger.debug("Inizializzo connessione a Google Drive API.")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


def create_drive_folder(service, name, parent_id):
    """
    Crea una cartella su Google Drive all'interno della cartella padre specificata.

    Args:
        service: oggetto Google Drive API autenticato
        name (str): nome della nuova cartella
        parent_id (str): ID della cartella padre su Drive

    Returns:
        str: ID della cartella creata, oppure None in caso di errore
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
        return None


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

    except HttpError as e:
        logger.error(f"❌ Errore durante la ricerca della cartella '{name}': {e}")
        return None


def download_drive_pdfs_recursively(service, folder_id, destination, drive_id):
    """
    Scarica tutti i PDF ricorsivamente da una cartella di Drive all'output locale.
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
                request = service.files().get_media(fileId=file_id)
                local_path = Path(destination) / name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with io.FileIO(local_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                logger.info(f"📥 Scaricato PDF: {name}")

            elif mime_type == 'application/vnd.google-apps.folder':
                new_dest = Path(destination) / name
                new_dest.mkdir(parents=True, exist_ok=True)
                download_drive_pdfs_recursively(service, file_id, new_dest, drive_id)

    except HttpError as e:
        logger.error(f"❌ Errore nel download ricorsivo: {e}")


def download_drive_pdfs_to_local(service, config):
    """
    Scarica tutti i PDF dalla cartella cliente su Drive all'output locale.
    Usa config dict: deve avere slug, drive_id, output_path.
    """
    slug = config["slug"]
    drive_id = config["drive_id"]
    output_path = config["output_path"]
    logger.info(f"📥 Inizio download PDF per il cliente: {slug}")
    folder = find_drive_folder_by_name(service, slug, drive_id)
    if not folder:
        logger.error(f"❌ Cartella '{slug}' non trovata su Drive con ID: {drive_id}")
        return False
    folder_id = folder["id"]
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
            return False

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
            return False

        logger.info("📁 Inizio creazione struttura cartelle da YAML...")
        create_nested_folders(parent_folder_id, root_folders)
        logger.info("✅ Struttura cartelle creata con successo.")
        return True

    except Exception as e:
        logger.error(f"❌ Errore nella lettura del file YAML o creazione delle sottocartelle: {e}")
        return False
