import sys
import argparse
import subprocess
from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import CONFIG_FILE_NAME
from pipeline.exceptions import PipelineError, ConfigError, DriveDownloadError
from pipeline.context import ClientContext
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.path_utils import is_safe_subpath
from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
)
from pipeline.gitbook_preview import run_gitbook_docker_preview
from pipeline.github_utils import push_output_to_github
from pipeline.env_utils import get_env_var


def is_docker_running() -> bool:
    """Controlla se Docker è in esecuzione."""
    try:
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def validate_client_config_schema(config_path: Path, slug: str):
    """Valida la config del cliente e solleva errori con contesto."""
    import yaml
    required_keys = {"drive_raw_folder_id"}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore apertura/parsing config: {e}",
                          slug=slug, file_path=config_path)

    missing = required_keys - set(cfg.keys())
    if missing:
        raise ConfigError(
            f"Config client mancante di chiavi obbligatorie: {missing}",
            slug=slug,
            file_path=config_path
        )


def onboarding_full_main(slug: str, dry_run: bool = False, no_drive: bool = False, interactive_mode: bool = True):
    """Esegue l'onboarding completo per il cliente specificato."""
    logger = get_structured_logger("onboarding_full")
    context = ClientContext.load(slug, logger=logger)
    logger.info("🚀 Avvio onboarding completo", extra={"slug": context.slug})

    try:
        # Validazione config cliente
        logger.info("📑 Validazione configurazione cliente...", extra={"slug": slug})
        client_config_path = Path(f"output/timmy-kb-{slug}/config/{CONFIG_FILE_NAME}")
        if not client_config_path.exists():
            raise ConfigError("Config client non trovato", slug=slug, file_path=client_config_path)
        validate_client_config_schema(client_config_path, slug)
        logger.info("✅ Configurazione cliente valida", extra={"slug": slug})

        drive_raw_folder_id = context.settings.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("ID cartella RAW su Drive mancante", slug=slug)

        if dry_run:
            logger.info("🏃 Modalità dry-run: nessun download da Drive", extra={"slug": slug})
            return

        # Download PDF
        if not no_drive:
            logger.info("📥 Avvio download PDF da Google Drive...", extra={"slug": slug})
            drive_service = get_drive_service(context)
            if not is_safe_subpath(context.raw_dir, context.base_dir):
                raise PipelineError("Percorso RAW non sicuro", slug=slug, file_path=context.raw_dir)
            download_drive_pdfs_to_local(drive_service, context, drive_raw_folder_id, context.raw_dir)
            logger.info("✅ Download PDF completato", extra={"slug": slug, "drive_id": drive_raw_folder_id})

        # Conversione PDF → MD
        logger.info("📄 Avvio conversione PDF in Markdown...", extra={"slug": slug})
        if not is_safe_subpath(context.md_dir, context.base_dir):
            raise PipelineError("Percorso MD non sicuro", slug=slug, file_path=context.md_dir)
        convert_files_to_structured_markdown(context)
        logger.info("✅ Conversione completata", extra={"slug": slug})

        # Generazione SUMMARY e README
        logger.info("📝 Generazione SUMMARY.md e README.md...", extra={"slug": slug})
        generate_summary_markdown(context)
        generate_readme_markdown(context)
        logger.info("✅ SUMMARY.md e README.md generati", extra={"slug": slug})

        # Preview GitBook
        if interactive_mode:
            logger.info("🌐 Avvio anteprima GitBook...", extra={"slug": slug})
            if not is_docker_running():
                raise PipelineError("Docker non in esecuzione", slug=slug)
            run_gitbook_docker_preview(context, wait_on_exit=True)
            logger.info("✅ Anteprima GitBook completata", extra={"slug": slug})
        else:
            logger.info("Anteprima GitBook saltata o chiusa automaticamente", extra={"slug": slug})

        # Push GitHub
        logger.info("📤 Avvio push su GitHub...", extra={"slug": slug})
        github_token = get_env_var("GITHUB_TOKEN")
        if not github_token:
            logger.warning("🔒 GITHUB_TOKEN non impostato", extra={"slug": slug})
        else:
            if interactive_mode:
                confirm = input("Vuoi eseguire il push su GitHub? (y/n): ").strip().lower()
                if confirm != "y":
                    logger.info("⏭️ Push GitHub saltato dall'utente", extra={"slug": slug})
                    logger.info("🎯 Onboarding completato senza push GitHub", extra={"slug": slug})
                    return
            push_output_to_github(context, github_token, confirm_push=True)
            logger.info("✅ Push GitHub completato", extra={"slug": slug})

        logger.info("🎯 Onboarding completato con successo", extra={"slug": slug})

    except DriveDownloadError as e:
        logger.error(f"📦 Errore download PDF: {e}", extra={"slug": slug})
        raise
    except (PipelineError, ConfigError) as e:
        logger.error(f"❌ Errore onboarding: {e}", extra={"slug": slug})
        raise
    except Exception as e:
        logger.error(f"❌ Errore imprevisto: {e}", extra={"slug": slug}, exc_info=True)
        raise PipelineError(str(e), slug=slug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--dry-run", action="store_true", help="Esegui senza download da Drive")
    parser.add_argument("--no-drive", action="store_true", help="Salta download da Drive")
    args = parser.parse_args()

    # Determina modalità interattiva
    interactive_mode = sys.stdin.isatty()

    # Recupero slug
    if not args.slug:
        if get_env_var("TEST_MODE") == "1":
            slug = "test-client"
            interactive_mode = False
        elif interactive_mode:
            slug = input("🔑 Inserisci lo slug cliente (es: acme-srl): ").strip()
        else:
            raise ConfigError("Slug mancante in modalità batch")
    else:
        slug = args.slug

    onboarding_full_main(
        slug=slug,
        dry_run=args.dry_run,
        no_drive=args.no_drive,
        interactive_mode=interactive_mode
    )
