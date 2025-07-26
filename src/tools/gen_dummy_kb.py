import os
from pathlib import Path
import yaml

BASE = Path("filetest/timmy-kb-dummy")
BOOK = BASE / "book"
CONFIG = BASE / "config"

def main():
    # Crea cartelle
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

    # config.yaml
    config = {
        "slug": "dummy",
        "cliente_nome": "Dummy KB",
        "output_path": "output/timmy-kb-dummy",
        "md_output_path": "output/timmy-kb-dummy/book",
        # Altri parametri opzionali se servono...
    }
    config_file = CONFIG / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)

    print(f"✅ Struttura dummy KB creata in: {BASE.resolve()}")

if __name__ == "__main__":
    main()
