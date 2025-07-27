from pathlib import Path
import subprocess
import os

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
from pipeline.cleanup import cleanup_output_folder, safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_recursively
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.exceptions import PipelineError
from pipeline.settings import get_settings
from pipeline.utils import is_valid_slug


def check_docker_running():
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


os.environ["MUPDF_WARNING_SUPPRESS"] = "1"


def main():
    logger = get_structured_logger("onboarding_full", "logs/onboarding.log")
    logger.info("▶️ Avvio pipeline onboarding Timmy-KB")
    print("▶️ Onboarding completo Timmy-KB")

    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Configurazione globale non valida: {e}")
        logger.error(f"❌ Errore configurazione globale: {e}")
        return

    if not check_docker_running():
        print("❌ Docker non risulta attivo o non è raggiungibile.")
        print("🔧 Avvia Docker Desktop o il servizio Docker prima di continuare.")
        logger.error("Docker non attivo: pipeline bloccata.")
        return

    try:
        raw_slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto da input: '{raw_slug}'")
        slug = raw_slug.replace("_", "-")
        if not is_valid_slug(slug):
            print("❌ Slug cliente non valido. Ammessi solo lettere minuscole, numeri, trattini (es: acme-srl).")
            logger.error(f"❌ Slug cliente non valido: '{raw_slug}' -> '{slug}'")
            return

        print("📥 Caricamento configurazione...")
        cfg = get_config(slug)
        config = cfg.config
        secrets = cfg.secrets

        logger.info(f"✅ Config caricato e validato per cliente: {slug}")
        logger.debug(f"Config: {config.dict()}")

        print(f"📝 Onboarding per: {slug}")

        # Step 1: Download da Drive
        cleanup_output_folder(config.dict())
        service = get_drive_service()
        raw_dir = Path(config.md_output_path).parent / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        download_drive_pdfs_recursively(
            service=service,
            folder_id=secrets.DRIVE_ID,
            destination=raw_dir,
            drive_id=secrets.DRIVE_ID
        )
        logger.info("📥 Download PDF da Drive completato.")

        config_dict = config.dict()
        config_dict["raw_dir"] = str(raw_dir)

        pdf_files = list(raw_dir.rglob("*.pdf"))
        if not pdf_files:
            logger.warning("⚠️ Nessun PDF trovato nella cartella raw dopo il download.")
            print("❌ Nessun PDF trovato: pipeline interrotta.")
            return

        print("📚 Conversione PDF → Markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown(config_dict, mapping)
        logger.info("✅ Conversione PDF → Markdown completata.")

        print("🧠 Estrazione semantica (enrichment)...")
        enrich_markdown_folder(config.md_output_path, slug)
        logger.info("✅ Enrichment semantico completato.")

        print("📑 Generazione SUMMARY.md e README.md...")
        md_files = [f for f in os.listdir(config.md_output_path) if f.endswith(".md")]
        generate_summary_markdown(md_files, config.md_output_path)
        generate_readme_markdown(config.md_output_path, slug)
        logger.info("✅ SUMMARY.md e README.md generati.")

        print("🔍 Avvio anteprima GitBook in locale con Docker...")
        run_gitbook_docker_preview(config_dict)
        logger.info("✅ Anteprima GitBook completata.")

        risposta = input("❓ Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
        logger.debug(f"Risposta push GitHub: {risposta}")
        temp_dir = None
        if risposta == "y":
            print("🚀 Esecuzione push su GitHub SOLO per la knowledge base (cartella book)...")
            book_config = config_dict.copy()
            book_config["output_path"] = str(Path(config.md_output_path).resolve())
            book_config["github_repo"] = f"{settings.github_org}/timmy-kb-{slug}"
            logger.info(f"🔗 Repo GitHub: {book_config['github_repo']}")
            temp_dir = push_output_to_github(book_config)
            logger.info(f"✅ Push su GitHub completato. Temp dir: {temp_dir}")
            print(f"✅ Push su GitHub completato. File temporanei in: {temp_dir}")
        else:
            logger.info("⏹️ Push GitHub annullato.")
            print("⏹️ Push annullato.")

        if temp_dir:
            while True:
                finale = input(f"\n✅ Onboarding completato per {slug}? [y/N] ").strip().lower()
                if finale == "y":
                    safe_clean_dir(temp_dir)
                    print("🧹 Pulizia completata. Onboarding chiuso.")
                    logger.info("🧹 Temp dir rimossa.")
                    break
                elif finale == "n":
                    reset = input("🔄 Vuoi azzerare la procedura? [y/N] ").strip().lower()
                    if reset == "y":
                        also_conf = input("🗑️ Cancellare anche la configurazione? [y/N] ").strip().lower()
                        if also_conf == "y":
                            config_dir = Path(config.md_output_path).parent / "config"
                            safe_clean_dir(config_dir)
                            print("🗑️ Tutto azzerato.")
                            logger.warning("🗑️ Config rimossa.")
                        safe_clean_dir(temp_dir)
                        print("🧹 Onboarding azzerato.")
                        logger.info("🧹 Temp dir rimossa.")
                        break
                    elif reset == "n":
                        print(f"❗ La temp dir ({temp_dir}) e la config rimangono.")
                        logger.warning("❗ Temp dir non rimossa.")
                        break
                else:
                    print("Risposta non valida. Inserisci 'y' o 'n'.")
        else:
            print(f"🏁 Onboarding completato per: {slug}")
            logger.info(f"🏁 Onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore bloccante: {e}")
        print(f"❌ Errore bloccante: {e}")
        return
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        print(f"❌ Errore imprevisto: {e}")
        return


if __name__ == "__main__":
    main()
