import os
from pathlib import Path
import shutil
import yaml

BASE = Path("output/timmy-kb-dummy")
BOOK = BASE / "book"
CONFIG = BASE / "config"
RAW_DEST = BASE / "raw"
RAW_SRC = Path("filetest/raw")  # Cartella di partenza con i pdf dummy
DUMMY_REPO = Path("filetest/dummy_repo")

def main():
    # Crea cartelle principali
    BOOK.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)

    # README.md
    readme = BOOK / "README.md"
    readme.write_text("# Dummy KB – Test\n\nQuesta è una knowledge base di test generata automaticamente.\n")

    # SUMMARY.md
    summary = BOOK / "SUMMARY.md"
    summary.write_text(
        "# Sommario\n\n"
        "* [Introduzione](README.md)\n"
        "* [Test Markdown](test.md)\n"
    )

    # test.md (contenuto minimale)
    test_md = BOOK / "test.md"
    test_md.write_text(
        "# Test Markdown\n\n"
        "Questo è un file markdown di esempio per testare la pipeline Honkit.\n"
        "- Punto uno\n"
        "- Punto due\n"
    )

    # config.yaml — tutti i campi obbligatori!
    config = {
        "slug": "dummy",
        "cliente_nome": "Dummy KB",
        "raw_dir": "raw",                     # CAMPO OBBLIGATORIO per la pipeline
        "md_output_path": "book",             # CAMPO OBBLIGATORIO per la pipeline
        "output_path": "output/timmy-kb-dummy",
    }
    config_file = CONFIG / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)

    print(f"✅ Struttura dummy KB creata in: {BASE.resolve()}")

    # OPZIONE: Copia filetest/raw in output/timmy-kb-dummy/raw
    if RAW_SRC.exists():
        resp = input("\nVuoi copiare la cartella filetest/raw/ (PDF e sottocartelle) in output/timmy-kb-dummy/raw? [y/N]: ").strip().lower()
        if resp == "y":
            if RAW_DEST.exists():
                shutil.rmtree(RAW_DEST)
            shutil.copytree(RAW_SRC, RAW_DEST)
            print(f"✅ Cartella RAW copiata in: {RAW_DEST.resolve()}")
        else:
            print("ℹ️  Salto copia cartella RAW.")
    else:
        print("⚠️  Cartella filetest/raw non trovata, nessuna copia effettuata.")

    # OPZIONE: Crea cartella dummy_repo per test GitHub
    resp_repo = input("\nVuoi creare anche la cartella filetest/dummy_repo per i test GitHub? [y/N]: ").strip().lower()
    if resp_repo == "y":
        if DUMMY_REPO.exists():
            shutil.rmtree(DUMMY_REPO)
        DUMMY_REPO.mkdir(parents=True, exist_ok=True)
        (DUMMY_REPO / "README.md").write_text("# Dummy Repo per test GitHub\n\nQuesta cartella viene usata dai test automatici.")
        (DUMMY_REPO / "test.txt").write_text("File di test\n")
        print(f"✅ Cartella dummy_repo creata in: {DUMMY_REPO.resolve()}")
    else:
        print("ℹ️  Salto creazione cartella dummy_repo.")

if __name__ == "__main__":
    main()
