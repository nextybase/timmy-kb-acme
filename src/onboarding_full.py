import os
import sys
import argparse
import subprocess
from pathlib import Path
import yaml

from dotenv import load_dotenv
from pydantic import ValidationError

from pipeline.logging_utils import get_structured_logger
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

load_dotenv()
os.environ["MUPDF_WARNING_SUPPRESS"] = "1"


def load_client_config(slug: str, output_dir: Path) -> dict:
    """Carica il config.yaml specifico del cliente da path dinamico."""
    config_path = output_dir / f"timmy-kb-{slug}" / "config" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config cliente non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f), config_path


def check_docker_running() -> bool:
    """Verifica che Docker sia attivo ed eseguibile sul sistema."""
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
    """Orchestra il full onboarding pipeline per Timmy-KB."""
    if not slug:
        if no_interactive:
            raise PipelineError("Slug non fornito in modalità no-interactive.")
        slug = input("🔑 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}. Ammessi solo lettere, numeri e trattini.")

    from pipeline.config_utils import get_settings_for_slug
    settings = get_settings_for_slug(slug)

    logger = get_structured_logger("onboarding_full", str(settings.logs_path))
    logger.info("🚀 Avvio pipeline onboarding Timmy-KB")
    logger.debug(f"Slug: {slug} | Settings.DRIVE_ID: {getattr(settings, 'DRIVE_ID', None)}")

    try:
        if not skip_preview:
            if not check_docker_running():
                logger.error("Docker non attivo o non raggiungibile. Pipeline bloccata.")
                raise PipelineError("Docker non attivo o non raggiungibile.")

        logger.info(f"📄 Config caricato e validato per cliente: {slug}")
        logger.debug(f"Settings: {settings.model_dump()}")

        client_config, config_path = load_client_config(slug, settings.output_dir)

        drive_folder_id = client_config.get("drive_folder_id")
        if not drive_folder_id:
            logger.critical("❌ ERRORE BLOCCANTE: drive_folder_id mancante!")
            logger.debug(f"Config cliente letto da {config_path}: {client_config}")
            logger.debug(f"Slug: {slug} | DRIVE_ID (.env): {getattr(settings, 'DRIVE_ID', None)}")
            logger.debug(f"File config.yaml esiste: {config_path.exists()} | Path: {config_path.resolve()}")
            raise PipelineError(
                f"ID cartella cliente (drive_folder_id) mancante nel config! "
                f"Path: {config_path.resolve()} | Slug: {slug}"
            )

        output_base = settings.output_dir
        raw_dir = settings.raw_dir
        md_dir = settings.md_output_path

        logger.info("🧹 Pulizia cartelle di output (book e raw)...")
        safe_clean_dir(md_dir)
        safe_clean_dir(raw_dir)

        service = get_drive_service(settings)
        raw_dir.mkdir(parents=True, exist_ok=True)
        download_drive_pdfs_to_local(
            service=service,
            settings=settings,
            drive_folder_id=drive_folder_id,
            drive_id=settings.DRIVE_ID
        )
        logger.info("📥 Download PDF da Drive completato.")

        logger.info("🔄 Conversione PDF -> markdown strutturato...")
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown()
        logger.info("✅ Conversione markdown completata.")

        logger.info("💡 Arricchimento semantico markdown...")
        enrich_markdown_folder(md_dir)
        logger.info("✅ Arricchimento semantico completato.")

        logger.info("📝 Generazione SUMMARY.md e README.md...")
        md_files = [f for f in md_dir.iterdir() if f.suffix == ".md"]
        generate_summary_markdown(md_files, md_dir)
        generate_readme_markdown(md_dir)
        logger.info("✅ SUMMARY.md e README.md generati.")

        if skip_preview:
            logger.info("[SKIP] Preview Docker saltata.")
        else:
            logger.info("🐋 Avvio preview GitBook con Docker...")
            run_gitbook_docker_preview()
            logger.info("✅ Preview GitBook completata.")

        do_push = auto_push
        if not auto_push and not no_interactive:
            resp = input("🤖 Vuoi procedere con il push su GitHub della sola cartella book? [y/N] ").strip().lower()
            do_push = (resp == "y")

        if do_push:
            push_output_to_github()
            logger.info(f"✅ Push GitHub completato. Cartella: {md_dir}")
        else:
            logger.info("Push GitHub annullato.")

        logger.info(f"✅ Onboarding completato per: {slug}")

    except PipelineError as e:
        logger.error(f"⚠️ Errore pipeline: {e}")
        raise
    except ValidationError as e:
        logger.error(f"❌ Errore validazione settings: {e}")
        raise PipelineError(e)
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Onboarding completo Timmy-KB (automazione pipeline)",
        epilog="Esempio: python onboarding.py --slug dummy --auto-push --skip-preview --no-interactive"
    )
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--no-interactive", action="store_true", help="Disabilita input interattivo (solo pipeline/CI)")
    parser.add_argument("--auto-push", action="store_true", help="Esegui sempre push GitHub senza conferma")
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
