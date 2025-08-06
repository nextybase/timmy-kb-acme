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

# Third-party packages
from dotenv import load_dotenv
from pydantic import ValidationError

# Local modules
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_config
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.cleanup import safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local  # <--- MODIFICA QUI
from pipeline.exceptions import PipelineError
from pipeline.utils import is_valid_slug
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping

# Esegui subito dopo gli import di terze parti
load_dotenv()

os.environ["MUPDF_WARNING_SUPPRESS"] = "1"

def check_docker_running():
    """
    Verifica che Docker sia attivo ed eseguibile sul sistema.

    Returns:
        bool: True se Docker risponde, False altrimenti.
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

    - Valida parametri e configurazione.
    - Pulizia cartelle di output e workspace.
    - Download dei PDF da Drive nella cartella "raw".
    - Conversione automatica PDF -> markdown strutturato.
    - Enrichment semantico del markdown.
    - Generazione SUMMARY.md e README.md.
    - Preview locale con Docker/Honkit (facoltativa).
    - Push su GitHub automatizzato o su richiesta.

    Args:
        slug (str, optional): Identificativo cliente/progetto (es: acme-srl).
        no_interactive (bool, optional): Disabilita input interattivo (modalità CI).
        auto_push (bool, optional): Esegui sempre push GitHub senza conferma.
        skip_preview (bool, optional): Salta la preview Docker/Honkit.

    Raises:
        PipelineError: Errori bloccanti nella pipeline o nella configurazione.
        ValidationError: Errori di validazione config (Pydantic).
        Exception: Errori imprevisti.
    """
    logger = get_structured_logger("onboarding_full", "logs/onboarding.log")
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
            raise PipelineError(f"Slug cliente non valido: '{slug}'")

        if not check_docker_running():
            logger.error("Docker non attivo o non raggiungibile. Pipeline bloccata.")
            raise PipelineError("Docker non attivo o non raggiungibile.")

        config = get_config(slug)
        logger.info(f"✅ Config caricato e validato per cliente: {slug}")
        logger.debug(f"Config: {config.model_dump()}")

        output_base = config.output_dir_path
        raw_dir = config.raw_dir_path
        md_dir = config.md_output_path_path

        logger.info("🧹 Pulizia cartelle di output (book e raw)...")
        safe_clean_dir(md_dir)
        safe_clean_dir(raw_dir)

        service = get_drive_service(slug)
        raw_dir.mkdir(parents=True, exist_ok=True)

        folder_id = getattr(config, "drive_folder_id", None)
        if not folder_id:
            logger.error("❌ ID cartella cliente (drive_folder_id) mancante nella config!")
            raise PipelineError("ID cartella cliente (drive_folder_id) mancante nella config!")

        # ---- MODIFICA: usa SOLO il wrapper/adaptor, non la funzione low-level ----
        download_drive_pdfs_to_local(
            service=service,
            config=config
        )
        logger.info("✅ Download PDF da Drive completato.")

        logger.info("🔄 Conversione PDF -> markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown(config)
        logger.info("✅ Conversione markdown completata.")

        logger.info("🔎 Enrichment semantico markdown...")
        enrich_markdown_folder(md_dir, slug)
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
            run_gitbook_docker_preview(config)
            logger.info("✅ Preview GitBook completata.")

        # Push automatico o con conferma manuale
        do_push = auto_push
        if not auto_push and not no_interactive:
            resp = input("🚀 Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
            logger.debug(f"Risposta push GitHub: {resp}")
            do_push = (resp == "y")

        if do_push:
            push_output_to_github(md_dir, config)
            logger.info(f"✅ Push GitHub completato. Cartella: {md_dir}")
        else:
            logger.info("Push GitHub annullato.")

        logger.info(f"✅ Onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore pipeline: {e}")
        raise
    except ValidationError as e:
        logger.error(f"❌ Errore validazione config: {e}")
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
