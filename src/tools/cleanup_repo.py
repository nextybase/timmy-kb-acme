#!/usr/bin/env python3
"""
Strumento autonomo di cleanup per la pipeline Timmy-KB.
Allineato alla versione NeXT v1.3:
- Configurazione centralizzata (TimmySecrets)
- Logging strutturato
"""

import os
import shutil
import subprocess
from pathlib import Path
import sys

# Setup import locale
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import TimmySecrets

# === Logger
logger = get_structured_logger("tools.cleanup_repo")

# === Configurazione centralizzata
try:
    secrets = TimmySecrets()
except Exception as e:
    print(f"❌ Errore caricando configurazione globale: {e}")
    sys.exit(1)

# === Percorsi base
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIENTI_BASE_PATH = Path(secrets.clienti_base_path)
OUTPUT_BASE_PATH = PROJECT_ROOT / "output"
BOOK_JSON_PATH = PROJECT_ROOT / "book.json"
PACKAGE_JSON_PATH = PROJECT_ROOT / "package.json"
BOOK_DIR = PROJECT_ROOT / "_book"
GITHUB_ORG = secrets.github_org or "nextybase"

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

def delete_file(path: Path, label: str):
    if path.exists():
        try:
            path.unlink()
            logger.info(f"🗑️  {label} eliminato: {path}")
        except Exception as e:
            logger.error(f"❌ Errore eliminando {label}: {e}")
    else:
        logger.info(f"📄 {label} non presente: {path}")

def delete_github_repo(repo_fullname: str):
    try:
        subprocess.run(["gh", "repo", "delete", repo_fullname, "--yes"], check=True)
        logger.info(f"✅ Repo GitHub eliminata: {repo_fullname}")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Errore GitHub CLI: {e}")

def run_cleanup(slug: str, elimina_repo: bool = True):
    slug = slug.strip().lower().replace("_", "-")
    folder_clienti = CLIENTI_BASE_PATH / f"timmy-kb-{slug}"
    folder_output  = OUTPUT_BASE_PATH / f"timmy-kb-{slug}"
    repo_fullname  = f"{GITHUB_ORG}/timmy-kb-{slug}"

    logger.info("🔍 Avvio procedura di cleanup completa...")
    delete_folder(folder_clienti, "Cartella clienti")
    clear_folder(folder_output, "Cartella output")

    delete_file(BOOK_JSON_PATH, "book.json")
    delete_file(PACKAGE_JSON_PATH, "package.json")
    delete_folder(BOOK_DIR, "_book (build Docker)")

    if elimina_repo:
        logger.info(f"🔄 Eliminazione repo GitHub: {repo_fullname}")
        delete_github_repo(repo_fullname)

    logger.info("✅ Cleanup completo terminato.")

def main():
    slug = input("🆔 Inserisci lo slug cliente da eliminare (es: prova): ").strip().lower()
    repo_fullname = f"{GITHUB_ORG}/timmy-kb-{slug}"

    print(f"\n🚨 ATTENZIONE: stai per eliminare:")
    print(f"- Cartella clienti: {CLIENTI_BASE_PATH / f'timmy-kb-{slug}'}")
    print(f"- Cartella output:  {OUTPUT_BASE_PATH / f'timmy-kb-{slug}'}")
    print(f"- File book.json:   {BOOK_JSON_PATH}")
    print(f"- File package.json:{PACKAGE_JSON_PATH}")
    print(f"- Cartella _book/:  {BOOK_DIR}")
    print(f"- Repo GitHub:      {repo_fullname}")
    conferma = input("✋ Confermi? Scrivi 'ok' per procedere: ").strip().lower()

    if conferma == "ok":
        run_cleanup(slug, elimina_repo=True)
    else:
        logger.info("⛔ Operazione annullata dall'utente.")

if __name__ == "__main__":
    main()
