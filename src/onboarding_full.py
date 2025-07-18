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

# Google Drive API imports per download PDF
from googleapiclient.discovery import build
from google.oauth2 import service_account

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def download_pdfs_from_drive(service, drive_id, slug, temp_dir):
    """
    Trova la cartella raw del cliente e scarica TUTTI i PDF in temp_dir,
    inclusi quelli in sottocartelle (ricorsivo).
    """
    def get_folder_id_by_name(parent_id, name):
        q = f"'{parent_id}' in parents and name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
        res = service.files().list(q=q, spaces='drive', supportsAllDrives=True,
                                   includeItemsFromAllDrives=True, corpora='drive',
                                   driveId=drive_id, fields="files(id)").execute()
        if not res["files"]:
            return None
        return res["files"][0]["id"]

    def download_pdfs_recursively(folder_id, relative_path=""):
        # Scarica tutti i PDF di questa cartella
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

        # Trova tutte le sottocartelle e processale ricorsivamente
        q = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
        res = service.files().list(q=q, spaces='drive', supportsAllDrives=True,
                                   includeItemsFromAllDrives=True, corpora='drive',
                                   driveId=drive_id, fields="files(id, name)").execute()
        for folder in res["files"]:
            subfolder_id = folder["id"]
            subfolder_name = folder["name"]
            download_pdfs_recursively(subfolder_id, os.path.join(relative_path, subfolder_name))

    # 1. Trova cartella cliente
    cliente_folder_id = get_folder_id_by_name(drive_id, slug)
    if not cliente_folder_id:
        raise Exception(f"Cartella cliente '{slug}' non trovata.")

    # 2. Trova cartella raw
    raw_id = get_folder_id_by_name(cliente_folder_id, "raw")
    if not raw_id:
        raise Exception(f"Cartella 'raw' non trovata per '{slug}'.")

    # 3. Scarica PDF ricorsivo
    download_pdfs_recursively(raw_id)

def main():
    print("▶️ Onboarding completo Timmy-KB")
    slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
    if not slug:
        print("❌ Lo slug non può essere vuoto.")
        sys.exit(1)

    logger.info("📥 Caricamento configurazione...")
    config = load_config_from_drive(slug, {"slug": slug})

    print(f"📝 Onboarding per: {config.get('cliente_nome', config['slug'])}")

    # --- Scarica i PDF dal Drive (anche in sottocartelle) ---
    service_account_file = config.get("service_account_file", "service_account.json")
    drive_id = config.get("drive_id") or config.get("DRIVE_ID") or os.getenv("DRIVE_ID")
    if not drive_id:
        logger.error("❌ DRIVE_ID non trovato nel config né nelle variabili d'ambiente.")
        sys.exit(1)
    scopes = ["https://www.googleapis.com/auth/drive"]

    service = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes))
    temp_dir = Path(tempfile.gettempdir()) / f"timmykb_rawpdf_{slug}"
    download_pdfs_from_drive(service, drive_id, slug, temp_dir)
    config["drive_input_path"] = str(temp_dir)  # PATCH: i PDF sono ora in temp_dir

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
    