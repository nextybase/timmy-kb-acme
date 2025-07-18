import sys
import logging
import tempfile
from pathlib import Path
import os

from ingest.config_loader import load_config_from_drive
from ingest.pdf_to_md import convert_pdfs_to_markdown
from ingest.semantic_extractor import extract_semantics
from ingest.build_summary import build_markdown_summary
from ingest.gitbook_preview import launch_gitbook_preview
from ingest.github_push import do_push, ask_push
from ingest.cleanup import cleanup_output
from utils.github_utils import repo_exists  # ✅ nuovo import

# Google Drive API imports
from googleapiclient.discovery import build
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def download_pdfs_from_drive(service, drive_id, slug, temp_dir):
    def get_folder_id_by_name(parent_id, name):
        q = f"'{parent_id}' in parents and name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
        res = service.files().list(q=q, spaces='drive', supportsAllDrives=True,
                                   includeItemsFromAllDrives=True, corpora='drive',
                                   driveId=drive_id, fields="files(id)").execute()
        return res["files"][0]["id"] if res["files"] else None

    def download_pdfs_recursively(folder_id, relative_path=""):
        q = f"'{folder_id}' in parents and mimeType = 'application/pdf'"
        res = service.files().list(q=q, spaces='drive', supportsAllDrives=True,
                                   includeItemsFromAllDrives=True, corpora='drive',
                                   driveId=drive_id, fields="files(id, name)").execute()
        from googleapiclient.http import MediaIoBaseDownload
        for f in res["files"]:
            file_id = f["id"]
            file_name = f["name"]
            out_dir = Path(temp_dir) / relative_path
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / file_name
            request = service.files().get_media(fileId=file_id)
            with open(out_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            logger.info(f"Scaricato: {out_path}")

        q = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        res = service.files().list(q=q, spaces='drive', supportsAllDrives=True,
                                   includeItemsFromAllDrives=True, corpora='drive',
                                   driveId=drive_id, fields="files(id, name)").execute()
        for folder in res["files"]:
            download_pdfs_recursively(folder["id"], os.path.join(relative_path, folder["name"]))

    cliente_folder_id = get_folder_id_by_name(drive_id, slug)
    if not cliente_folder_id:
        raise Exception(f"Cartella cliente '{slug}' non trovata.")
    raw_id = get_folder_id_by_name(cliente_folder_id, "raw")
    if not raw_id:
        raise Exception(f"Cartella 'raw' non trovata per '{slug}'.")
    download_pdfs_recursively(raw_id)

def main():
    print("▶️ Onboarding completo Timmy-KB")
    slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
    if not slug:
        print("❌ Lo slug non può essere vuoto.")
        sys.exit(1)

    # === EARLY CHECK: repo già esistente su GitHub ===
    github_owner = os.getenv("GITHUB_ORG", "nextybase")
    repo_name = f"timmy-kb-{slug}"
    if repo_exists(github_owner, repo_name):
        print(f"⚠️  La repository '{github_owner}/{repo_name}' esiste già su GitHub.")
        scelta = input("🔁 Vuoi continuare comunque con l'onboarding? [y/N] ").strip().lower()
        if scelta != "y":
            print("⛔ Operazione annullata.")
            sys.exit(0)

    logger.info("📥 Caricamento configurazione...")
    config = load_config_from_drive(slug, {"slug": slug})

    print(f"📝 Onboarding per: {config.get('cliente_nome', config['slug'])}")

    service_account_file = config.get("service_account_file", "service_account.json")
    drive_id = config.get("drive_id") or os.getenv("DRIVE_ID")
    if not drive_id:
        logger.error("❌ DRIVE_ID non trovato nel config né nelle variabili d'ambiente.")
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/drive"]
    service = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes))

    temp_dir = Path(tempfile.gettempdir()) / f"timmykb_rawpdf_{slug}"
    download_pdfs_from_drive(service, drive_id, slug, temp_dir)
    config["drive_input_path"] = str(temp_dir)

    logger.info("📚 Conversione PDF → Markdown...")
    convert_pdfs_to_markdown(config)

    logger.info("🧠 Estrazione semantica...")
    extract_semantics(config)

    logger.info("📑 Generazione SUMMARY.md e README.md...")
    build_markdown_summary(config)

    logger.info("🔍 Avvio anteprima GitBook in locale con Docker...")
    launch_gitbook_preview(config["slug"])

    if ask_push(config):
        logger.info("🚀 Esecuzione push su GitHub...")
        do_push(config)
    else:
        logger.info("⛔ Push annullato dall’utente.")

    logger.info("🧹 Pulizia finale interattiva (opzionale)...")
    cleanup_output(config)

if __name__ == "__main__":
    main()
