import sys
import argparse
from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import CONFIG_FILE_NAME
from pipeline.exceptions import PipelineError, ConfigError, DriveDownloadError
from pipeline.context import ClientContext
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.path_utils import is_safe_subpath
from pipeline.content_utils import convert_files_to_structured_markdown  # ✅ Conversione PDF → MD

def onboarding_full_main(slug: str, dry_run: bool = False):
    """Esegue l'onboarding completo del cliente specificato."""
    context = ClientContext.load(slug)
    logger = get_structured_logger("onboarding_full", context=context)
    logger.info(f"🚀 Avvio onboarding completo per cliente: {context.slug}")

    try:
        # Recupera ID cartella RAW da config
        drive_raw_folder_id = context.settings.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("ID cartella RAW su Drive mancante in config.yaml")

        if dry_run:
            logger.info("🏁 Modalità dry-run attiva. Interrompo prima del download.")
            return

        # Connessione a Drive
        drive_service = get_drive_service(context)

        # Download PDF da Drive
        logger.info("📥 Download PDF da Drive...")
        if not is_safe_subpath(context.raw_dir, context.base_dir):
            raise PipelineError(f"Percorso RAW non sicuro: {context.raw_dir}")

        download_drive_pdfs_to_local(drive_service, context, drive_raw_folder_id, context.raw_dir)

        # ✅ Conversione PDF → Markdown
        if not is_safe_subpath(context.md_dir, context.base_dir):
            raise PipelineError(f"Percorso MD non sicuro: {context.md_dir}")

        convert_files_to_structured_markdown(context.raw_dir, context.md_dir)
        logger.info(f"📄 Conversione PDF → Markdown completata in: {context.md_dir}")

        # TODO: Generazione Book
        logger.info(f"✅ Onboarding completo terminato per cliente: {context.slug}")

    except (PipelineError, ConfigError, DriveDownloadError) as e:
        logger.error(f"❌ Errore onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"💥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--dry-run", action="store_true", help="Esegui solo parte locale senza interazione con Drive")
    args = parser.parse_args()

    # Modalità interattiva
    if not args.slug:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()

    try:
        onboarding_full_main(slug=args.slug, dry_run=args.dry_run)
    except PipelineError:
        sys.exit(1)
