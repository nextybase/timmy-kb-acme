"""
Procedura di onboarding completa Timmy-KB:
- Scarica file PDF dal Drive cliente
- Converte PDF in Markdown
- Aggiorna struttura locale e book
"""

import sys
import argparse
from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.context import ClientContext
from pipeline.drive_utils import download_drive_pdfs_to_local, get_drive_service
from pipeline.path_utils import is_safe_subpath
from pipeline.exceptions import PipelineError


def onboarding_full_main(slug: str, no_interactive: bool = False, dry_run: bool = False):
    """Esegue l'onboarding completo di un cliente."""
    context = ClientContext.load(slug)
    logger = get_structured_logger("onboarding_full", context=context)
    logger.info(f"🚀 Avvio onboarding completo per cliente: {context.slug}")

    try:
        # ✅ Validazione path di lavoro
        if not is_safe_subpath(context.raw_dir, context.base_dir):
            raise PipelineError(f"Path raw_dir non sicuro: {context.raw_dir}")
        if not is_safe_subpath(context.md_dir, context.base_dir):
            raise PipelineError(f"Path md_dir non sicuro: {context.md_dir}")

        # Controllo presenza ID cartella Drive
        drive_raw_folder_id = context.settings.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise PipelineError(
                "ID cartella 'drive_raw_folder_id' mancante nel config. "
                "Esegui prima pre_onboarding.py per generare la struttura."
            )

        # Scarica PDF da Drive (se non in dry-run)
        if not dry_run:
            logger.info("📥 Download PDF da Drive...")
            drive_service = get_drive_service(context)
            download_drive_pdfs_to_local(
                service=drive_service,
                context=context,
                drive_folder_id=drive_raw_folder_id,
                local_path=context.raw_dir
            )

        # TODO: Conversione PDF → MD (da implementare)
        # logger.info("🛠 Conversione PDF in Markdown...")
        # convert_pdfs_to_md(context.raw_dir, context.md_dir)

        # TODO: Generazione Book (da implementare)
        # logger.info("📚 Generazione Book...")
        # build_book(context)

        logger.info(f"✅ Onboarding completo terminato per cliente: {context.slug}")

    except PipelineError as e:
        logger.error(f"❌ Errore onboarding: {e}")
        raise
    except Exception as e:
        logger.error(f"💥 Errore imprevisto: {e}", exc_info=True)
        raise PipelineError(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Onboarding completo Timmy-KB")
    parser.add_argument("--slug", type=str, help="Slug cliente (es: acme-srl)")
    parser.add_argument("--no-interactive", action="store_true", help="Salta richieste interattive")
    parser.add_argument("--dry-run", action="store_true", help="Esegui senza operazioni esterne")
    args = parser.parse_args()

    # Modalità interattiva
    if not args.slug and not args.no_interactive:
        args.slug = input("🔹 Inserisci lo slug cliente (es: acme-srl): ").strip()

    try:
        onboarding_full_main(slug=args.slug, no_interactive=args.no_interactive, dry_run=args.dry_run)
    except PipelineError:
        sys.exit(1)
