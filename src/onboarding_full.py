"""
onboarding_full.py

Orchestratore principale per il processo di onboarding documentale Timmy-KB.
Automatizza la validazione della configurazione, download e conversione PDF,
enrichment semantico, generazione markdown, preview GitBook e push su GitHub.
"""

# Standard library
import os
import sys
import argparse
import subprocess
from pathlib import Path
import yaml

# Third-party packages
from dotenv import load_dotenv
from pydantic import ValidationError

# Local modules
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import settings
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup import safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.exceptions import PipelineError
from pipeline.utils import is_valid_slug
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping

# Esegui subito dopo gli import di terze parti
load_dotenv()

os.environ["MUPDF_WARNING_SUPPRESS"] = "1"

def load_client_config(slug: str) -> dict:
    """
    Carica il config.yaml specifico del cliente.
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config cliente non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def check_docker_running():
    """
    Verifica che Docker sia attivo ed eseguibile sul sistema.
    """
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def onboarding_main(
    slug=None,
    no_interactive=False,
    auto_push=False,
    skip_preview=False
):
    """
    Orchestrates the full onboarding pipeline for Timmy-KB.
    """
    logger = get_structured_logger("onboarding_full", str(settings.logs_path))
    logger.info("▶️ Avvio pipeline onboarding Timmy-KB")

    try:
        # Slug: da CLI o fallback a input()
        if not slug:
            if no_interactive:
                logger.error("Slug non fornito in modalità no-interactive. Uscita.")
                raise PipelineError("Slug non fornito in modalità no-interactive.")
            slug = input("🔤 Inserisci lo slug cliente: ").strip().lower()
        logger.debug(f"Slug ricevuto: '{slug}'")
        slug = slug.replace("_", "-")
        if not is_valid_slug(slug):
            logger.error(f"Slug cliente non valido: '{slug}'. Ammessi solo lettere, numeri, trattini (es: acme-srl).")
            raise PipelineError(f"Slug cliente non valido: {slug}")

        # Setta la variabile SLUG nell'ambiente così settings la usa subito dopo
        os.environ["SLUG"] = slug

        if not check_docker_running():
            logger.error("Docker non attivo o non raggiungibile. Pipeline bloccata.")
            raise PipelineError("Docker non attivo o non raggiungibile.")

        logger.info(f"✅ Config caricato e validato per cliente: {slug}")
        logger.debug(f"Settings: {settings.model_dump()}")

        # --- PATCH: carica config cliente per drive_folder_id ---
        client_config = load_client_config(slug)
        drive_folder_id = client_config.get("drive_folder_id")
        if not drive_folder_id:
            logger.error("❌ ID cartella cliente (drive_folder_id) mancante nel config!")
            raise PipelineError("ID cartella cliente (drive_folder_id) mancante nel config!")

        output_base = settings.output_dir
        raw_dir = settings.raw_dir
        md_dir = settings.md_output_path

        logger.info("🧹 Pulizia cartelle di output (book e raw)...")
        safe_clean_dir(md_dir)
        safe_clean_dir(raw_dir)

        service = get_drive_service()
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Download PDF da Drive su raw_dir
        download_drive_pdfs_to_local(
            service=service,
            drive_folder_id=drive_folder_id,   # id cartella cliente
            drive_id=settings.DRIVE_ID         # id shared drive
        )

        logger.info("✅ Download PDF da Drive completato.")

        logger.info("🔄 Conversione PDF -> markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown()
        logger.info("✅ Conversione markdown completata.")

        logger.info("🔎 Enrichment semantico markdown...")
        enrich_markdown_folder(md_dir)
        logger.info("✅ Enrichment semantico completato.")

        logger.info("📚 Generazione SUMMARY.md e README.md...")
        md_files = [f for f in md_dir.iterdir() if f.suffix == ".md"]
        generate_summary_markdown(md_files, md_dir)
        generate_readme_markdown(md_dir)
        logger.info("✅ SUMMARY.md e README.md generati.")

        if skip_preview:
            logger.info("[SKIP] Preview Docker saltata.")
        else:
            logger.info("👁️  Avvio preview GitBook con Docker...")
            run_gitbook_docker_preview()
            logger.info("✅ Preview GitBook completata.")

        # Push automatico o con conferma manuale
        do_push = auto_push
        if not auto_push and not no_interactive:
            resp = input("🚀 Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
            logger.debug(f"Risposta push GitHub: {resp}")
            do_push = (resp == "y")

        if do_push:
            push_output_to_github()
            logger.info(f"✅ Push GitHub completato. Cartella: {md_dir}")
        else:
            logger.info("Push GitHub annullato.")

        logger.info(f"✅ Onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore pipeline: {e}")
        raise
    except ValidationError as e:
        logger.error(f"❌ Errore validazione settings: {e}")
        raise PipelineError(e)
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)

if __name__ == "__main__":
    """
    Avvia la procedura di onboarding Timmy-KB da CLI.
    Parametri supportati:
      --slug           Identificativo cliente/progetto (es: acme-srl)
      --no-interactive Disabilita input interattivo (solo pipeline/CI)
      --auto-push      Esegui push GitHub senza chiedere conferma
      --skip-preview   Salta preview Docker/Honkit
    """
    parser = argparse.ArgumentParser(
        description="Onboarding completo Timmy-KB (automazione pipeline)",
        epilog="Esempio: python onboarding.py --slug dummy --auto-push --skip-preview --no-interactive"
    )
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--no-interactive", action="store_true", help="Disabilita input interattivo (solo pipeline/CI)")
    parser.add_argument("--auto-push", action="store_true", help="Esegui sempre push GitHub senza chiedere conferma")
    parser.add_argument("--skip-preview", action="store_true", help="Salta la preview Docker/Honkit")

    args = parser.parse_args()
    try:
        onboarding_main(
            slug=args.slug,
            no_interactive=args.no_interactive,
            auto_push=args.auto_push,
            skip_preview=args.skip_preview
        )
    except PipelineError:
        sys.exit(1)
