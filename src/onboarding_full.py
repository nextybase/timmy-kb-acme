import os
from pathlib import Path
from utils.logger_utils import get_logger
from ingest.config_loader import load_config
from ingest.pdf_to_md import convert_pdfs_to_markdown
from semantic.semantic_extractor import enrich_markdown_folder
from ingest.build_summary import generate_summary_md, generate_readme_md
from ingest.gitbook_preview import run_gitbook_preview
from ingest.github_push import do_push
from ingest.cleanup import cleanup_output
from utils.drive_utils import get_drive_service, download_pdfs_from_drive

logger = get_logger("onboarding_full", "logs/onboarding.log")

def main():
    print("▶️ Onboarding completo Timmy-KB")
    slug = input("🔤 Inserisci lo slug cliente: ").strip()
    print("📥 Caricamento configurazione...")

    config = load_config(slug)
    logger.info(f"✅ Config caricato e arricchito per cliente: {slug}")
    print(f"📝 Onboarding per: {config['cliente_nome']}")

    # Step 1: Download da Drive
    cleanup_output(config)
    try:
        service = get_drive_service()
        download_pdfs_from_drive(
            service=service,
            slug=config["slug"],
            drive_id=config["drive_id"],
            local_dir=config["output_path"]
        )
    except Exception as e:
        logger.error(f"❌ Errore nel download PDF da Drive: {e}")
        return

    # PATCH: allinea il path di input per la conversione ai PDF realmente scaricati
    config["raw_dir"] = str(Path(config["output_path"]) / "raw")
    logger.info(f"[PATCH] Imposto config['raw_dir'] a {config['raw_dir']}")

    # Step 2: Conversione PDF → Markdown
    print("📚 Conversione PDF → Markdown...")
    convert_pdfs_to_markdown(config)

    # Step 3: Estrazione Semantica JSON
    print("🧠 Estrazione semantica...")
    enrich_markdown_folder(config["output_path"])

    # Step 4: Generazione README.md e SUMMARY.md
    print("📑 Generazione SUMMARY.md e README.md...")
    md_path = config["md_output_path"]
    md_files = [f for f in os.listdir(md_path) if f.endswith(".md")]
    generate_summary_md(md_files, md_path)
    generate_readme_md(md_path, slug)

    # Step 5: Preview GitBook
    print("🔍 Avvio anteprima GitBook in locale con Docker...")
    run_gitbook_preview(config)

    # Step 6: Push GitHub
    risposta = input("❓ Vuoi procedere con il push su GitHub? [y/N] ").strip().lower()
    if risposta == "y":
        print("🚀 Esecuzione push su GitHub...")
        do_push(config)
    else:
        print("⏹️ Push annullato. Operazione completata.")

if __name__ == "__main__":
    main()
