import os
import yaml
from pathlib import Path
from fpdf import FPDF

# === CONFIG ===
RAW_YAML = "config/cartelle_raw.yaml"
PDF_DUMMY_YAML = "config/pdf_dummy.yaml"
BASE_OUTPUT = Path("filetest/raw")  # output generato qui

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
    pdf.output(pdf_path)
    print(f"📄 Generato PDF di test: {pdf_path}")

def main():
    # Carica yaml struttura e contenuti dummy
    cartelle_struct = load_yaml(RAW_YAML)
    pdf_dummy = load_yaml(PDF_DUMMY_YAML)
    cartelle = parse_cartelle_structure(cartelle_struct)

    print(f"\n🗂️  Genero struttura e PDF dummy in: {BASE_OUTPUT}\n")
    for cat in cartelle:
        cat_folder = BASE_OUTPUT / cat
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

    print("\n✅ PDF dummy generati per tutte le cartelle tematiche!")

if __name__ == "__main__":
    main()
