import os
from pathlib import Path
from dotenv import load_dotenv
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import load_client_config
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup import cleanup_output_folder
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.exceptions import PipelineError

load_dotenv()
logger = get_structured_logger("onboarding_full", "logs/onboarding.log")

def main():
    """
    Pipeline di onboarding Timmy-KB:
    1. Download PDF da Drive nella cartella raw locale
    2. Conversione PDF → Markdown strutturato
    3. Enrichment semantico (se richiesto)
    4. Generazione README.md e SUMMARY.md
    5. Preview con Docker, push su GitHub (opzionale)
    """
    logger.info("▶️ Avvio pipeline onboarding Timmy-KB")
    print("▶️ Onboarding completo Timmy-KB")

    try:
        # --- Input slug ---
        slug = input("🔤 Inserisci lo slug cliente: ").strip()
        logger.debug(f"Slug ricevuto da input: '{slug}'")
        if not slug:
            print("❌ Slug cliente non valido.")
            logger.error("❌ Slug cliente mancante: operazione annullata.")
            return

        # --- Caricamento config cliente ---
        print("📥 Caricamento configurazione...")
        config = load_client_config(slug)
        logger.info(f"✅ Config caricato e arricchito per cliente: {slug}")
        logger.debug(f"Config: {config}")

        print(f"📝 Onboarding per: {config['cliente_nome']}")

        # --- Step 1: Download da Drive e pulizia output ---
        cleanup_output_folder(config)
        service = get_drive_service()
        download_drive_pdfs_to_local(service=service, config=config)
        logger.info("📥 Download PDF da Drive completato.")

        # --- Aggiorna config["raw_dir"] ---
        config["raw_dir"] = str(Path(config["output_path"]) / "raw")
        logger.debug(f"PATCH: config['raw_dir'] impostato a {config['raw_dir']}")

        # --- Check presenza PDF dopo download ---
        pdf_files = list(Path(config["raw_dir"]).rglob("*.pdf"))
        if not pdf_files:
            logger.warning("⚠️ Nessun PDF trovato nella cartella raw dopo il download. Controllare che il cliente abbia caricato i file su Drive.")
            print("❌ Nessun PDF trovato: pipeline interrotta.")
            return

        # --- Step 2: Conversione PDF → Markdown strutturato ---
        print("📚 Conversione PDF → Markdown strutturato...")
        mapping = load_semantic_mapping()  # mapping yaml caricato UNA SOLA VOLTA
        convert_files_to_structured_markdown(config, mapping)
        logger.info("✅ Conversione PDF → Markdown completata.")

        # --- Step 3: Enrichment semantico ---
        print("🧠 Estrazione semantica (enrichment)...")
        enrich_markdown_folder(config["md_output_path"], slug)
        logger.info("✅ Enrichment semantico completato.")

        # --- Step 4: Generazione README.md e SUMMARY.md (UNA SOLA VOLTA) ---
        print("📑 Generazione SUMMARY.md e README.md...")
        md_path = config["md_output_path"]
        md_files = [f for f in os.listdir(md_path) if f.endswith(".md")]
        generate_summary_markdown(md_files, md_path)
        generate_readme_markdown(md_path, slug)
        logger.info("✅ SUMMARY.md e README.md generati.")

        # --- Step 5: Preview GitBook ---
        print("🔍 Avvio anteprima GitBook in locale con Docker...")
        run_gitbook_docker_preview(config)
        logger.info("✅ Anteprima GitBook completata.")

        # --- Step 6: Push GitHub ---
        risposta = input("❓ Vuoi procedere con il push su GitHub? [y/N] ").strip().lower()
        logger.debug(f"Risposta push GitHub: {risposta}")
        if risposta == "y":
            print("🚀 Esecuzione push su GitHub...")
            push_output_to_github(config)
            logger.info("✅ Push su GitHub completato.")
        else:
            logger.info("⏹️ Push su GitHub annullato dall’utente.")
            print("⏹️ Push annullato. Operazione completata.")

        logger.info(f"🏁 Onboarding pipeline completata per cliente: {slug}")
        print(f"🏁 Onboarding pipeline completata per cliente: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore bloccante nella pipeline: {e}")
        print(f"❌ Errore bloccante: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore non gestito: {e}")
        print(f"❌ Errore imprevisto: {e}")
        return

if __name__ == "__main__":
    main()
