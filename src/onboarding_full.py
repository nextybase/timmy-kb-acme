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
from pipeline.github_utils import push_output_to_github, github_api_call
from pipeline.cleanup import safe_clean_dir
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local, drive_api_call
from pipeline.exceptions import (
    PipelineError,
    DriveDownloadError,
    PushError,
    ConfigError,
)
from pipeline.utils import is_valid_slug
from pipeline.config_utils import get_settings_for_slug
from semantic.semantic_extractor import enrich_markdown_folder
from semantic.semantic_mapping import load_semantic_mapping
from pipeline.constants import BACKUP_SUFFIX

load_dotenv()
os.environ["MUPDF_WARNING_SUPPRESS"] = "1"


def load_client_config(slug: str, output_dir: Path) -> dict:
    """
    Carica il config.yaml specifico del cliente da path dinamico.
    """
    config_path = output_dir / "config" / "config.yaml"
    if not config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f), config_path


def check_docker_running() -> bool:
    """
    Verifica che Docker sia attivo ed eseguibile.
    """
    try:
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except Exception:
        return False


def validate_and_clean_dir(target_path: Path, settings_base: Path, logger) -> None:
    """
    Valida che la directory sia interna a BASE_DIR prima del cleanup.
    """
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(settings_base.resolve())):
            raise PipelineError(f"Cleanup bloccato: {target_path} non è all'interno di BASE_DIR")
        safe_clean_dir(target_path)
        logger.info(f"✅ Pulizia completata per {target_path}")
    except Exception as e:
        logger.error(f"❌ Errore nella pulizia di {target_path}: {e}")
        raise


def onboarding_main(slug=None, no_interactive=False, auto_push=False, skip_preview=False):
    """
    Orchestrazione full onboarding Timmy-KB.
    """
    if not slug:
        if no_interactive:
            raise PipelineError("Slug mancante in modalità no-interactive.")
        slug = input("📝 Inserisci lo slug cliente: ").strip()

    slug = slug.replace("_", "-").lower()
    if not is_valid_slug(slug):
        raise PipelineError(f"Slug cliente non valido: {slug}.")

    settings = get_settings_for_slug(slug)
    logger = get_structured_logger("onboarding_full", str(settings.logs_path))
    logger.info("🚀 Avvio pipeline onboarding Timmy-KB")
    logger.debug(f"Slug: {slug} | DRIVE_ID: {getattr(settings, 'DRIVE_ID', None)}")

    try:
        if not skip_preview:
            if not check_docker_running():
                logger.error("Docker non attivo o non raggiungibile. Pipeline bloccata.")
                raise PipelineError("Docker non attivo o non raggiungibile.")

        logger.info(f"📂 Config caricata per cliente: {slug}")
        logger.debug(f"Settings: {settings.model_dump()}")

        client_config, config_path = load_client_config(slug, settings.output_dir)

        drive_folder_id = client_config.get("drive_folder_id")
        if not drive_folder_id:
            logger.critical("🚫 DRIVE_FOLDER_ID mancante!")
            raise DriveDownloadError(f"Config cliente {config_path} privo di drive_folder_id")

        # Cleanup sicuro
        validate_and_clean_dir(settings.md_output_path, settings.base_dir, logger)
        validate_and_clean_dir(settings.raw_dir, settings.base_dir, logger)

        # Download Drive
        drive_service = get_drive_service(settings)
        drive_api_call(
            download_drive_pdfs_to_local,
            service=drive_service,
            settings=settings,
            drive_folder_id=drive_folder_id,
            drive_id=settings.DRIVE_ID
        )
        logger.info("📥 Download PDF da Drive completato.")

        # Conversione PDF → Markdown
        mapping = load_semantic_mapping()
        convert_files_to_structured_markdown(settings=settings)
        logger.info("✏️ Conversione markdown completata.")

        # Enrichment semantico
        enrich_markdown_folder(settings.md_output_path)
        logger.info("🏷️ Enrichment semantico completato.")

        # SUMMARY e README
        md_files = [f for f in settings.md_output_path.iterdir() if f.suffix == ".md"]
        generate_summary_markdown(md_files, settings.md_output_path)
        generate_readme_markdown(settings.md_output_path)
        logger.info("📚 SUMMARY.md e README.md generati.")

        # Preview
        if skip_preview:
            logger.info("[SKIP] Preview Docker saltata.")
        else:
            logger.info("👀 Avvio preview GitBook con Docker...")
            run_gitbook_docker_preview()
            logger.info("🔍 Preview GitBook completata.")

        # Push GitHub
        if not auto_push and not no_interactive:
            resp = input("🚀 Vuoi procedere con il push su GitHub? [y/N] ").strip().lower()
            do_push = (resp == "y")
        else:
            do_push = auto_push

        if do_push:
            github_api_call(push_output_to_github, settings, md_dir_path=settings.md_output_path)
            logger.info(f"✅ Push GitHub completato per cartella: {settings.md_output_path}")
        else:
            logger.info("Push GitHub annullato.")

        logger.info(f"🏁 Onboarding completato per: {slug}")

    except (PipelineError, DriveDownloadError, PushError, ConfigError) as e:
        logger.error(f"❌ Errore pipeline: {e}")
        raise
    except ValidationError as e:
        logger.error(f"⚠️ Errore validazione settings: {e}")
        raise PipelineError(e)
    except Exception as e:
        logger.error(f"🔥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Onboarding completo Timmy-KB (automazione pipeline)",
        epilog="Esempio: python onboarding.py --slug dummy --auto-push --skip-preview --no-interactive"
    )
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--no-interactive", action="store_true", help="Disabilita input interattivo")
    parser.add_argument("--auto-push", action="store_true", help="Esegue push GitHub senza conferma")
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
