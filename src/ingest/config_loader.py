import os
import yaml
import tempfile
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from dotenv import load_dotenv
from pathlib import Path
from io import BytesIO

# Caricamento .env dinamico
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
DRIVE_ID = os.getenv("DRIVE_ID")
REPO_CLONE_BASE = os.getenv("REPO_CLONE_BASE", ".")
RAW_DIR_TEMPLATE = os.getenv("RAW_DIR_TEMPLATE", "{base_drive}/{slug}/raw")
OUTPUT_DIR_TEMPLATE = os.getenv("OUTPUT_DIR_TEMPLATE", "output/timmy_kb_{slug}")
BASE_DRIVE = os.getenv("BASE_DRIVE", "G:/Drive condivisi/Nexty Docs")
GITHUB_ORG = os.getenv("GITHUB_ORG", "nextybase")
REPO_VISIBILITY = os.getenv("REPO_VISIBILITY", "private")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config_from_drive(slug: str, override: dict = {}) -> dict:
    # === CONTROLLI PRELIMINARI ENV ===
    if not DRIVE_ID:
        raise EnvironmentError("❌ DRIVE_ID non trovato nelle variabili d'ambiente.")
    if not SERVICE_ACCOUNT_FILE or not Path(SERVICE_ACCOUNT_FILE).exists():
        raise EnvironmentError("❌ SERVICE_ACCOUNT_FILE mancante o non trovato.")
    if not BASE_DRIVE:
        raise EnvironmentError("❌ BASE_DRIVE non definito nel .env.")
    if not RAW_DIR_TEMPLATE or not OUTPUT_DIR_TEMPLATE:
        raise EnvironmentError("❌ RAW_DIR_TEMPLATE o OUTPUT_DIR_TEMPLATE mancanti nel .env.")

    # === CLIENT GOOGLE DRIVE ===
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds)

    # === CERCA CARTELLA CLIENTE SU DRIVE ===
    query = f"'{DRIVE_ID}' in parents and name = '{slug}' and mimeType = 'application/vnd.google-apps.folder'"
    response = service.files().list(
        q=query,
        spaces='drive',
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora='drive',
        driveId=DRIVE_ID,
        fields="files(id, name)"
    ).execute()
    folders = response.get("files", [])

    if not folders:
        raise FileNotFoundError(f"❌ Cartella '{slug}' non trovata nel Drive condiviso.")

    folder_id = folders[0]["id"]

    # === CERCA config.yaml ===
    query = f"'{folder_id}' in parents and name = 'config.yaml'"
    response = service.files().list(
        q=query,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora='drive',
        driveId=DRIVE_ID,
        spaces='drive',
        fields="files(id, name)"
    ).execute()
    files = response.get("files", [])

    if not files:
        raise FileNotFoundError("❌ File di configurazione 'config.yaml' non trovato nella cartella.")

    file_id = files[0]["id"]
    request = service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    config_data = yaml.safe_load(fh)

    # === COSTRUZIONE PATH DINAMICI DA TEMPLATE ===
    repo_name = config_data.get("repo_name", f"timmy-kb-{slug}")
    github_owner = config_data.get('github_owner', GITHUB_ORG)
    repo_path = os.path.join(REPO_CLONE_BASE, repo_name)

    drive_input_path = RAW_DIR_TEMPLATE.format(
        slug=slug,
        base_drive=BASE_DRIVE
    )
    md_output_path = OUTPUT_DIR_TEMPLATE.format(
        slug=slug
    )

    config_data.update({
        "slug": slug,
        "repo_name": repo_name,
        "github_owner": github_owner,
        "github_repo": f"{github_owner}/{repo_name}",
        "repo_visibility": REPO_VISIBILITY,
        "repo_path": repo_path,
        "md_output_path": md_output_path,
        "drive_input_path": drive_input_path
    })

    if override:
        config_data.update(override)

    # Salva una copia temporanea della config risolta per debug/tracing
    tmp_file_path = Path(tempfile.gettempdir()) / f"config_{slug}.yaml"
    with open(tmp_file_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    logger.info(f"✅ Config caricato e arricchito per cliente: {slug}")
    return config_data
