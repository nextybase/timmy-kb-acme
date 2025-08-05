from pathlib import Path
import subprocess
import os
from dotenv import load_dotenv
load_dotenv()

from pydantic import ValidationError

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_config
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup import safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_recursively
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.exceptions import PipelineError
from pipeline.utils import is_valid_slug

os.environ["MUPDF_WARNING_SUPPRESS"] = "1"

def check_docker_running():
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def check_gitbook_preview_files(md_dir: Path):
    print("⚡ [SKIP_PREVIEW] Controllo file minimi per preview GitBook...")
    warn_files = []
    if not md_dir.exists():
        warn_files.append("Cartella book/ NON creata dalla pipeline.")
    elif not list(md_dir.rglob("*.md")):
        warn_files.append("Almeno un file .md in book/ (es. test.md)")

    if warn_files:
        print("\n⚠️  [WARNING] Alcuni file minimi per la preview GitBook sono mancanti:")
        for w in warn_files:
            print(f"   - {w}")
        print("➡️  Rigenera la cartella dummy prima di lanciare la preview.")
    else:
        print("✅ File minimi per preview GitBook OK.")
    print("👉  **Per la preview completa, eseguire manualmente o usare il test dedicato.**")

def main():
    logger = get_structured_logger("onboarding_full", "logs/onboarding.log")
    logger.info("▶️ Avvio pipeline onboarding Timmy-KB")
    print("▶️ Onboarding completo Timmy-KB")

    if not check_docker_running():
        print("⚠️ Docker non risulta attivo o non è raggiungibile.")
        logger.error("Docker non attivo: pipeline bloccata.")
        return

    try:
        raw_slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug cliente non valido. Ammessi solo lettere, numeri, trattini (es: acme-srl).")
            logger.error(f"Slug cliente non valido: '{slug}'")
            return

        print("📥 Caricamento configurazione...")
        config = get_config(slug)
        logger.info(f"✅ Config caricato e validato per cliente: {slug}")
        logger.debug(f"Config: {config.model_dump()}")

        output_base = config.output_dir_path
        raw_dir = config.raw_dir_path
        md_dir = config.md_output_path_path

        print("🧹 Pulizia cartelle di output (book e raw)...")
        safe_clean_dir(md_dir)
        safe_clean_dir(raw_dir)

        service = get_drive_service(slug)
        raw_dir.mkdir(parents=True, exist_ok=True)

        folder_id = getattr(config, "drive_folder_id", None)
        if not folder_id:
            logger.error("❌ ID cartella cliente (drive_folder_id) mancante nella config!")
            print("❌ Errore: ID cartella cliente mancante nella config!")
            return

        download_drive_pdfs_recursively(
            service=service,
            folder_id=folder_id,
            raw_dir_path=raw_dir,
            drive_id=config.secrets.DRIVE_ID
        )
        logger.info("✅ Download PDF da Drive completato.")

        print("🔄 Conversione PDF -> markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown(config, mapping)
        logger.info("✅ Conversione markdown completata.")

        print("🔎 Enrichment semantico markdown...")
        enrich_markdown_folder(md_dir, slug)
        logger.info("✅ Enrichment semantico completato.")

        print("📚 Generazione SUMMARY.md e README.md...")
        md_files = [f for f in md_dir.iterdir() if f.suffix == ".md"]
        generate_summary_markdown(md_files, md_dir)
        generate_readme_markdown(md_dir)
        logger.info("✅ SUMMARY.md e README.md generati.")

        if os.environ.get("TIMMY_SKIP_PREVIEW") == "1":
            print("👁️  [SKIP] Preview Docker disabilitata.")
            check_gitbook_preview_files(md_dir)
            logger.info("[SKIP] Preview Docker saltata.")
        else:
            print("👁️  Avvio preview GitBook con Docker...")
            run_gitbook_docker_preview(config)
            logger.info("✅ Preview GitBook completata.")

        resp = input("🚀 Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
        logger.debug(f"Risposta push GitHub: {resp}")
        if resp == "y":
            push_output_to_github(md_dir, config)
            logger.info(f"✅ Push GitHub completato. Cartella: {md_dir}")
            print(f"✅ Push GitHub completato. Cartella: {md_dir}")
        else:
            logger.info("Push GitHub annullato dall'utente.")
            print("ℹ️  Push annullato.")

        print(f"✅ Onboarding completato per: {slug}")
        logger.info(f"✅ Onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore pipeline: {e}")
        print(f"❌ Errore pipeline: {e}")
    except ValidationError as e:
        logger.error(f"❌ Errore validazione config: {e}")
        print(f"❌ Errore validazione config: {e}")
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        print(f"❌ Errore imprevisto: {e}")

if __name__ == "__main__":
    main()
