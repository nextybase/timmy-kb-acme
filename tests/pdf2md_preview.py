import sys
import os
import shutil
from pathlib import Path

# Fix: aggiungi src/ al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from pipeline.settings import get_settings
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.gitbook_preview import run_gitbook_docker_preview

SLUG = "dummy"
settings = get_settings()
OUTPUT_BASE = f"output/timmy-kb-{SLUG}"
RAW_DIR = os.path.join(OUTPUT_BASE, "raw")     # <-- I PDF vanno qui
BOOK_DIR = os.path.join(OUTPUT_BASE, "book")   # <-- I Markdown qui
PDF_SRC_DIR = "filetest/pdf"

def setup_test_raw_dir(pdf_src_dir, raw_dir):
    if os.path.exists(raw_dir):
        shutil.rmtree(raw_dir)
    os.makedirs(raw_dir, exist_ok=True)
    for pdf in Path(pdf_src_dir).glob("*.pdf"):
        shutil.copy(pdf, raw_dir)

def cleanup_test_output(output_base):
    if os.path.exists(output_base):
        shutil.rmtree(output_base)
        print(f"🧹 Output test '{output_base}' eliminato.")
    else:
        print("Nessun output di test da eliminare.")

def main():
    config = {
        "slug": SLUG,
        "raw_dir": RAW_DIR,          # PDF in /raw/
        "output_path": OUTPUT_BASE,  # (root cliente)
        "md_output_path": BOOK_DIR,  # Markdown in /book/
    }

    print("📦 [PDF2MD] Setup raw dir con PDF di test...")
    setup_test_raw_dir(PDF_SRC_DIR, RAW_DIR)

    print("📚 [PDF2MD] Conversione PDF → Markdown strutturato...")
    mapping = load_semantic_mapping()
    convert_files_to_structured_markdown(config, mapping)

    print("📑 [PDF2MD] Generazione SUMMARY.md...")
    md_files = [f for f in os.listdir(BOOK_DIR) if f.endswith(".md")]
    generate_summary_markdown(md_files, BOOK_DIR)

    # Genera sempre anche il README.md (necessario per Honkit/GitBook)
    print("📝 [PDF2MD] Generazione README.md (richiesto da Honkit)...")
    generate_readme_markdown(BOOK_DIR, SLUG)

    print(f"✅ Trasformazione PDF→Markdown completata. Controlla i file in: {BOOK_DIR}")

    print("🔍 [PDF2MD] Avvio anteprima GitBook in locale con Docker...")
    try:
        run_gitbook_docker_preview(config)
    except Exception as e:
        print(f"❌ Errore durante la preview Docker: {e}")

    choice = input(f"\nVuoi eliminare i file di output generati per il test '{SLUG}'? [y/N] ").strip().lower()
    if choice == "y":
        cleanup_test_output(OUTPUT_BASE)
    else:
        print("❗ Output di test NON eliminato (ricorda di farlo manualmente quando non serve più).")

if __name__ == "__main__":
    main()
