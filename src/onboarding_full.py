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
    validate_markdown_dir
)

def onboarding_full_main(slug: str, dry_run: bool = False):
    """
    Esegue l'onboarding completo per il cliente specificato.

    Passi:
    1. Carica config cliente dalla cartella output/.
    2. Recupera ID cartella RAW da config.
    3. Scarica PDF da Drive in locale.
    4. Converte PDF in markdown strutturato.
    5. Genera SUMMARY.md e README.md.
    6. Valida la cartella book/.
    """
    # 📌 Forza l'uso del config cliente
    client_config_path = Path(f"output/timmy-kb-{slug}/config/{CONFIG_FILE_NAME}")
    if not client_config_path.exists():
        raise ConfigError(f"Config cliente non trovato: {client_config_path}")

    # Carica direttamente il ClientContext dal file cliente
    context = ClientContext(client_config_path)
    logger = get_structured_logger("onboarding_full", context=context)
    logger.info(f"🚀 Avvio onboarding completo per cliente: {context.slug}")

    try:
        # Recupera ID cartella RAW
        drive_raw_folder_id = context.settings.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("ID cartella RAW su Drive mancante in config.yml del cliente")

        if dry_run:
            logger.info("💡 Modalità dry-run attiva: interrotto prima del download.")
            return

        # Connessione a Drive
        drive_service = get_drive_service(context)

        # Download PDF
        logger.info("📥 Download PDF da Drive...")
        if not is_safe_subpath(context.raw_dir, context.base_dir):
            raise PipelineError(f"Percorso RAW non sicuro: {context.raw_dir}")
        download_drive_pdfs_to_local(drive_service, context, drive_raw_folder_id, context.raw_dir)

        # Conversione PDF → MD
        if not is_safe_subpath(context.md_dir, context.base_dir):
            raise PipelineError(f"Percorso MD non sicuro: {context.md_dir}")
        convert_files_to_structured_markdown(context)
        logger.info(f"📝 Conversione completata in: {context.md_dir}")

        # Generazione SUMMARY.md e README.md
        generate_summary_markdown(context)
        generate_readme_markdown(context)

        # Validazione cartella book/
        validate_markdown_dir(context)

        logger.info(f"📚 Onboarding completo terminato per cliente: {context.slug}")

    except DriveDownloadError as e:
        logger.error(f"❌ Errore nel download dei PDF: {e}")
        raise
    except (PipelineError, ConfigError) as e:
        logger.error(f"❌ Errore onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"⚠️ Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--dry-run", action="store_true", help="Esegue solo parte locale senza interazione con Drive")
    args = parser.parse_args()

    # Modalità interattiva se slug mancante
    if not args.slug:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()

    try:
        onboarding_full_main(slug=args.slug, dry_run=args.dry_run)
    except PipelineError:
        sys.exit(1)
