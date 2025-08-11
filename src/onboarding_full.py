import sys
import argparse
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


def validate_client_config_schema(config_path: Path):
    """Valida che il file di config cliente contenga le chiavi obbligatorie."""
    import yaml
    required_keys = {"drive_raw_folder_id"}
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    missing = required_keys - set(cfg.keys())
    if missing:
        raise ConfigError(f"Config client mancante di chiavi obbligatorie: {missing}")


def onboarding_full_main(slug: str, dry_run: bool = False, no_drive: bool = False, interactive_mode: bool = True):
    """
    Esegue l'onboarding completo per il cliente specificato.
    """
    client_config_path = Path(f"output/timmy-kb-{slug}/config/{CONFIG_FILE_NAME}")
    if not client_config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {client_config_path}")
    validate_client_config_schema(client_config_path)

    context = ClientContext.load(slug)
    logger = get_structured_logger("onboarding_full", context=context)
    logger.info(f"🚀 Avvio onboarding completo per cliente: {context.slug}")

    try:
        drive_raw_folder_id = context.settings.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("ID cartella RAW su Drive mancante in config.yaml del cliente")

        if dry_run:
            logger.info("🛠 Modalità dry-run: simulazione senza connessione a Drive")
            return

        drive_service = None
        if not no_drive:
            drive_service = get_drive_service(context)

        # Creazione cartelle locali se mancanti
        for dir_path in [context.md_dir, context.base_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        if not no_drive:
            logger.info("📥 Download PDF da Drive...")
            if not is_safe_subpath(context.raw_dir, context.base_dir):
                raise PipelineError(f"Percorso RAW non sicuro: {context.raw_dir}")
            download_drive_pdfs_to_local(drive_service, context, drive_raw_folder_id, context.raw_dir)

        # Conversione PDF → MD
        if not is_safe_subpath(context.md_dir, context.base_dir):
            raise PipelineError(f"Percorso MD non sicuro: {context.md_dir}")
        convert_files_to_structured_markdown(context)
        logger.info(f"📄 Conversione completata in: {context.md_dir}")

        # Generazione file sommario e README
        generate_summary_markdown(context)
        generate_readme_markdown(context)

        logger.info(f"✅ Onboarding completo terminato per cliente: {context.slug}")

        # Avvio anteprima GitBook in Docker solo se interattivo
        if interactive_mode:
            logger.info("🚀 Avvio anteprima GitBook in Docker...")
            run_gitbook_docker_preview(context)

        # Push su GitHub usando variabili da env_utils
        github_token = get_env_var("GITHUB_TOKEN")

        if not github_token:
            logger.warning("⚠️ Variabile GITHUB_TOKEN non impostata. Push su GitHub saltato.")
        else:
            push_output_to_github(context, github_token, interactive_mode=interactive_mode)
    
    except DriveDownloadError as e:
        logger.error(f"📂 Errore nel download dei PDF: {e}")
        raise
    except (PipelineError, ConfigError) as e:
        logger.error(f"⚠️ Errore onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--dry-run", action="store_true", help="Esegui solo parte locale senza interazione con Drive")
    parser.add_argument("--no-drive", action="store_true", help="Salta connessione a Drive, esegue da file locali già presenti")
    args = parser.parse_args()

    interactive_mode = not (args.slug and (args.dry_run or args.no_drive))

    if not args.slug:
        args.slug = input("📝 Inserisci lo slug cliente (es: acme-srl): ").strip()

    try:
        onboarding_full_main(
            slug=args.slug,
            dry_run=args.dry_run,
            no_drive=args.no_drive,
            interactive_mode=interactive_mode
        )
    except PipelineError:
        sys.exit(1)
