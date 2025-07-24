#!/usr/bin/env python3
"""
Strumento autonomo di cleanup per la pipeline Timmy-KB.
- Elimina la cartella clienti
- Svuota la cartella output
- Cancella file locali (es. book.json)
- Elimina la repo GitHub remota
Usa la configurazione centralizzata via Settings.
"""

import os
import shutil
import subprocess
import logging
from pathlib import Path
import sys

# Setup path e logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from pipeline.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

# Path di progetto e variabili globali (tutte da settings se disponibili)
PROJECT_ROOT      = Path(__file__).resolve().parents[1]
CLIENTI_BASE_PATH = Path(getattr(settings, "clienti_base_path", r"C:\Users\User\clienti"))
OUTPUT_BASE_PATH  = PROJECT_ROOT / "output"
BOOK_JSON_PATH    = PROJECT_ROOT / "book.json"
GITHUB_ORG        = getattr(settings, "github_org", "nextybase")

def on_rm_error(func, path, exc_info):
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        logger.error(f"❌ Errore rimuovendo {path}: {e}")

def delete_folder(folder: Path, label: str):
    if folder.exists():
        try:
            shutil.rmtree(folder, onerror=on_rm_error)
            logger.info(f"🧹 {label} eliminata: {folder}")
        except Exception as e:
            logger.error(f"❌ Errore nella rimozione di {label}: {e}")
    else:
        logger.info(f"📁 {label} non trovata: {folder}")

def clear_folder(folder: Path, label: str):
    if folder.exists():
        try:
            for item in folder.rglob("*"):
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, onerror=on_rm_error)
            logger.info(f"🧺 {label} svuotata: {folder}")
        except Exception as e:
            logger.error(f"❌ Errore nello svuotamento di {label}: {e}")
    else:
        logger.info(f"📂 {label} non trovata: {folder}")

def delete_file(file_path: Path, label: str):
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"🗑️  {label} eliminato: {file_path}")
        except Exception as e:
            logger.error(f"❌ Errore eliminando {label}: {e}")
    else:
        logger.info(f"📄 {label} non presente: {file_path}")

def delete_github_repo(repo_fullname: str):
    try:
        subprocess.run(["gh", "repo", "delete", repo_fullname, "--yes"], check=True)
        logger.info(f"✅ Repo GitHub eliminata: {repo_fullname}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Errore GitHub CLI: {e}")

def run_cleanup(slug: str, elimina_repo: bool = True):
    # Path coerenti con la pipeline attuale (trattino, non underscore)
    folder_clienti = CLIENTI_BASE_PATH / f"timmy-kb-{slug}"
    folder_output  = OUTPUT_BASE_PATH / f"timmy-kb-{slug}"
    repo_fullname  = f"{GITHUB_ORG}/timmy-kb-{slug}"

    logger.info("🔍 Avvio procedura di cleanup completa...")
    delete_folder(folder_clienti, "Cartella clienti")
    clear_folder(folder_output, "Cartella output")
    delete_file(BOOK_JSON_PATH, "File book.json")

    if elimina_repo:
        logger.info(f"🔄 Eliminazione repo GitHub: {repo_fullname}")
        delete_github_repo(repo_fullname)

    logger.info("✅ Cleanup completo terminato.")

def main():
    slug = input("🆔 Inserisci lo slug cliente da eliminare (es: prova): ").strip().lower()

    folder_clienti = CLIENTI_BASE_PATH / f"timmy-kb-{slug}"
    folder_output  = OUTPUT_BASE_PATH / f"timmy-kb-{slug}"
    repo_fullname  = f"{GITHUB_ORG}/timmy-kb-{slug}"

    print(f"\n🚨 ATTENZIONE: stai per eliminare:")
    print(f"- Cartella clienti: {folder_clienti}")
    print(f"- Contenuto cartella output: {folder_output}")
    print(f"- Repo GitHub:      {repo_fullname}")
    print(f"- File book.json:   {BOOK_JSON_PATH}")
    conferma = input("✋ Confermi? Scrivi 'ok' per procedere: ").strip().lower()

    if conferma == "ok":
        run_cleanup(slug, elimina_repo=True)
    else:
        logger.info("⛔ Operazione annullata dall'utente.")

if __name__ == "__main__":
    main()
