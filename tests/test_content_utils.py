import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import shutil
import pytest
from pathlib import Path

from pipeline.config_utils import get_config
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from semantic.semantic_mapping import load_semantic_mapping

SLUG = "dummy"
OUTPUT_BASE = Path(f"output/timmy-kb-{SLUG}")
RAW_DIR = OUTPUT_BASE / "raw"
BOOK_DIR = OUTPUT_BASE / "book"

@pytest.fixture
def setup_and_teardown_output():
    # Verifica presenza PDF (anche nelle sottocartelle)
    if not RAW_DIR.exists() or not any(RAW_DIR.rglob("*.pdf")):
        pytest.skip("❌ Nessun PDF di test presente in 'raw/' (neanche nelle sottocartelle). Genera prima con il tool di setup.")

    # Rimuove test.md se esiste
    test_md = BOOK_DIR / "test.md"
    if test_md.exists():
        test_md.unlink()
        print("🗑️  Rimosso test.md prima del test.")

    yield

    # Conferma per rimozione file Markdown generati
    choice = input("❓ Vuoi eliminare i Markdown generati dal test? [y/N] ").strip().lower()
    if choice == "y":
        for md_file in BOOK_DIR.glob("*.md"):
            if md_file.name not in ("README.md", "SUMMARY.md"):
                md_file.unlink()
                print(f"🧹 Rimosso file Markdown generato: {md_file.name}")
        test_md.write_text("# File di test\nQuesto file è usato per test GitBook preview.\n", encoding="utf-8")
        print("📄 Ricreato file test.md post-test.")
    else:
        print("ℹ️  File Markdown generati lasciati per ispezione.")

def test_pdf_to_markdown_conversion(setup_and_teardown_output):
    config = get_config(SLUG)
    mapping = load_semantic_mapping()

    convert_files_to_structured_markdown(config, mapping)

    md_files = list(config.md_output_path_path.glob("*.md"))
    assert len(md_files) > 0, "Nessun file Markdown generato!"

    generate_summary_markdown(md_files, config.md_output_path_path)
    assert (config.md_output_path_path / "SUMMARY.md").exists(), "SUMMARY.md non generato!"

    generate_readme_markdown(config.md_output_path_path)
    assert (config.md_output_path_path / "README.md").exists(), "README.md non generato!"
