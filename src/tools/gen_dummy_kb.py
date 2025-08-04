import os
import sys
from pathlib import Path
import shutil
import yaml

try:
    from fpdf import FPDF
except ImportError:
    print("Devi installare fpdf: pip install fpdf")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Devi installare python-dotenv: pip install python-dotenv")
    # Non è bloccante, le env verranno lette solo se già settate
    pass

BASE = Path("output/timmy-kb-dummy")
BOOK = BASE / "book"
CONFIG = BASE / "config"
RAW = BASE / "raw"
DUMMY_REPO = Path("output/timmy-kb-dummy/repo")

RAW_YAML = "config/cartelle_raw.yaml"
PDF_DUMMY_YAML = "config/pdf_dummy.yaml"

# ID reale della cartella dummy su Drive (da usare nei test)
HARDCODED_DUMMY_DRIVE_ID = "1C1L-BtruPfyQB3nZCeo6zpjm0g77O95J"
HARDCODED_DUMMY_FOLDER_ID = "12cLba2kKKF4YH_JBA19Kjwr0J8awQDVh"

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def parse_cartelle_structure(cartelle_yaml):
    """Estrae tutte le cartelle tematiche dalla struttura YAML di cartelle_raw."""
    def _extract_names(folders):
        result = []
        for item in folders:
            if "name" in item:
                result.append(item["name"])
            if "subfolders" in item and item["subfolders"]:
                result += _extract_names(item["subfolders"])
        return result
    return _extract_names(cartelle_yaml.get("root_folders", []))

def make_pdf(titolo, paragrafi, pdf_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.multi_cell(0, 10, titolo)
    pdf.ln(6)
    pdf.set_font("Arial", "", 12)
    for par in paragrafi:
        pdf.multi_cell(0, 8, par)
        pdf.ln(2)
    pdf.output(str(pdf_path))
    print(f"📄 Generato PDF di test: {pdf_path}")

def genera_raw_structure():
    if not (os.path.exists(RAW_YAML) and os.path.exists(PDF_DUMMY_YAML)):
        print(f"⚠️  File YAML di configurazione non trovati ({RAW_YAML}, {PDF_DUMMY_YAML}). Skipping RAW/PDF.")
        return

    cartelle_struct = load_yaml(RAW_YAML)
    pdf_dummy = load_yaml(PDF_DUMMY_YAML)
    cartelle = parse_cartelle_structure(cartelle_struct)

    print(f"\n🗂️  Genero struttura RAW con PDF dummy in: {RAW.resolve()}\n")
    for cat in cartelle:
        cat_folder = RAW / cat
        cat_folder.mkdir(parents=True, exist_ok=True)
        info = pdf_dummy.get(cat, {})
        titolo = info.get("titolo", f"Sezione: {cat.title()}")
        paragrafi = info.get("paragrafi", [
            "Questo è un paragrafo di esempio.",
            "Puoi personalizzare il contenuto dei PDF modificando pdf_dummy.yaml.",
            "Sezione tematica generica.",
        ])
        pdf_path = cat_folder / f"{cat}_dummy.pdf"
        make_pdf(titolo, paragrafi, pdf_path)
    print(f"\n✅ PDF dummy generati in: {RAW.resolve()}!\n")

def main():
    # 1. Crea cartelle principali
    for folder in [BOOK, CONFIG, RAW, DUMMY_REPO]:
        folder.mkdir(parents=True, exist_ok=True)

    # 2. Crea README.md e SUMMARY.md
    (BOOK / "README.md").write_text("# Dummy KB – Test\n\nQuesta è una knowledge base di test generata automaticamente.\n")
    (BOOK / "SUMMARY.md").write_text(
        "# Sommario\n\n* [Introduzione](README.md)\n* [Test Markdown](test.md)\n"
    )
    (BOOK / "test.md").write_text(
        "# Test Markdown\n\nQuesto è un file markdown di esempio per testare la pipeline Honkit.\n- Punto uno\n- Punto due\n"
    )

    # 3. Crea config.yaml usando variabili d'ambiente dove serve
    config = {
        "slug": "dummy",
        "client_name": "Dummy KB",
        "raw_dir": str(RAW),
        "md_output_path": str(BOOK),
        "output_dir": str(BASE),
        "drive_id": HARDCODED_DUMMY_DRIVE_ID,
        "drive_folder_id": HARDCODED_DUMMY_FOLDER_ID,
        "service_account_file": os.environ.get("SERVICE_ACCOUNT_FILE", "service_account.json"),
        "base_drive": os.environ.get("BASE_DRIVE", "dummy-base-folder"),
        "github_repo": os.environ.get("GITHUB_REPO", "nextybase/timmy-kb-dummy"),
        "github_branch": os.environ.get("GITHUB_BRANCH", "main"),
        "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "gitbook_token": os.environ.get("GITBOOK_TOKEN", ""),
    }
    with open(CONFIG / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)

    print(f"✅ Cartella base KB generata in: {BASE.resolve()}")

    # 4. Genera RAW con struttura da YAML e PDF dummy
    genera_raw_structure()

    # 5. OPZIONALE: Crea dummy_repo per test GitHub (cartella e README)
    resp_repo = input("\nVuoi creare anche la cartella output/timmy-kb-dummy/repo per i test GitHub? [y/N]: ").strip().lower()
    if resp_repo == "y":
        if DUMMY_REPO.exists():
            shutil.rmtree(DUMMY_REPO)
        DUMMY_REPO.mkdir(parents=True, exist_ok=True)
        (DUMMY_REPO / "README.md").write_text(
            "# Dummy Repo per test GitHub\n\nQuesta cartella viene usata per test automatici."
        )
        (DUMMY_REPO / "test.txt").write_text("File di test\n")
        print(f"✅ Cartella dummy_repo creata in: {DUMMY_REPO.resolve()}")
    else:
        print("⏭️  Salto creazione cartella dummy_repo.")

if __name__ == "__main__":
    main()
