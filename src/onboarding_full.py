#!/usr/bin/env python3
"""
Script principale di onboarding per la generazione della Knowledge Base
di un cliente a partire dai PDF, con preview e deploy GitHub.
"""

import sys
from pathlib import Path
from ingest.config_loader import load_config
from ingest.pdf_to_md import convert_pdfs_to_markdown
from ingest.build_summary import build_markdown_summary
from ingest.gitbook_preview import preview_with_docker, cleanup_output
from ingest.github_push import push_to_github

def main():
    if len(sys.argv) != 2:
        print("Usage: python onboarding_full.py <slug_cliente>")
        sys.exit(1)

    slug = sys.argv[1].strip().lower()

    # 🔧 Configurazione diretta da file system locale
    config_path = Path(f"G:/Drive condivisi/Nexty Docs/{slug}/config.yaml")
    config = load_config(config_path)

    # 2. Conversione PDF in Markdown
    convert_pdfs_to_markdown(config)

    # 3. Costruzione README.md e SUMMARY.md
    build_markdown_summary(config)

    # 4. Preview GitBook con Docker
    preview_with_docker(config["md_output_path"])

    # 5. Prompt utente per decidere se proseguire con il deploy
    proceed = input("Vuoi procedere al deploy su GitHub? [y/n] ").strip().lower()
    if proceed != "y":
        clean = input("Vuoi anche cancellare i file generati? [y/n] ").strip().lower()
        if clean == "y":
            cleanup_output(config["md_output_path"])
        print("❌ Onboarding annullato.")
        sys.exit(0)

    # 6. Push su GitHub
    push_to_github(
        md_output_path=config["md_output_path"],
        repo_url=config["github_repo"],
        branch=config["github_branch"]
    )

    print("✅ Onboarding completato con successo.")

if __name__ == "__main__":
    main()
