"""
cleanup_utils.py

Utility di pulizia sicura delle cartelle di output della pipeline Timmy-KB.
Permette di svuotare in sicurezza il contenuto di una directory (file e sottocartelle),
ma protegge root, home e directory critiche.

Modifiche:
- Import allineati a nuova architettura
- Gestione robusta di settings/slug
- Unificazione logica di cleanup_output_folder e safe_clean_dir
- Logging uniforme anche in CLI
"""

import shutil
import argparse
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug, _validate_path_in_base_dir
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME
from pipeline.exceptions import CleanupError, PipelineError

logger = get_structured_logger("pipeline.cleanup")


# -------------------------------------------------
# Risoluzione settings
# -------------------------------------------------
def _resolve_settings(settings=None, slug: Optional[str] = None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato settings, richiede slug o lo prende da ENV.
    """
    if settings:
        return settings
    if slug:
        return get_settings_for_slug(slug)
    raise PipelineError("Impossibile risolvere settings: fornire 'settings' o 'slug'.")


# -------------------------------------------------
# Pulizia sicura
# -------------------------------------------------
def cleanup_directory(folder_path: Path, settings=None, slug: Optional[str] = None):
    """
    Svuota in sicurezza il contenuto della cartella specificata (file e sottocartelle),
    lasciando intatta la cartella stessa.
    """
    settings = _resolve_settings(settings, slug)
    folder = Path(folder_path).resolve()

    try:
        _validate_path_in_base_dir(folder, settings.base_dir)
    except ValueError as e:
        logger.error(f"❌ Tentativo di pulire path non sicuro: {folder}")
        raise CleanupError(f"Tentativo di pulire path non sicuro: {folder}") from e

    if not folder.exists():
        logger.info(f"ℹ️ La cartella {folder} non esiste, nessuna azione necessaria.")
        return

    for item in folder.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
                logger.info(f"🗑️ Rimossa sottocartella: {item}")
            else:
                item.unlink()
                logger.info(f"🗑️ Rimosso file: {item}")
        except Exception as e:
            logger.warning(f"⚠️ Impossibile rimuovere {item}: {e}")


# Alias per retrocompatibilità
safe_clean_dir = cleanup_directory
cleanup_output_folder = cleanup_directory


# -------------------------------------------------
# Modalità interattiva
# -------------------------------------------------
def interactive_cleanup(settings=None, slug: Optional[str] = None):
    """
    Modalità CLI interattiva: chiede all’utente conferma per cancellare l’output_dir.
    """
    settings = _resolve_settings(settings, slug)
    default_folder = str(settings.output_dir)
    folder = input(f"\n[Timmy-KB] Inserisci il percorso della cartella da svuotare [default: {default_folder}]: ").strip()
    if not folder:
        folder = default_folder

    logger.info(f"Stai per svuotare: {folder}")
    confirm = input("Sei sicuro? [y/N]: ").strip().lower()
    if confirm == "y":
        try:
            cleanup_directory(folder, settings=settings)
            logger.info("✅ Pulizia completata.")
        except CleanupError as e:
            logger.error(f"Errore: {e}")
    else:
        logger.info("Operazione annullata.")


# -------------------------------------------------
# Entry point CLI
# -------------------------------------------------
def cli_cleanup():
    """
    Entry-point CLI: parsing argomenti e chiamata cleanup_directory().
    """
    parser = argparse.ArgumentParser(
        description="Svuota il contenuto di una cartella di output in modo sicuro.",
        epilog="Esempio: python cleanup_utils.py --folder output/timmy-kb-dummy/ --force"
    )
    parser.add_argument("--folder", type=str, help="Percorso della cartella da svuotare (default: settings.output_dir)")
    parser.add_argument("--slug", type=str, help="Slug cliente (necessario se non si fornisce settings)")
    parser.add_argument("--force", action="store_true", help="Esegue senza chiedere conferma")

    args = parser.parse_args()
    settings = _resolve_settings(slug=args.slug)

    folder = args.folder or str(settings.output_dir)
    if not args.force:
        logger.info(f"Attenzione: stai per svuotare {folder}")
        confirm = input("Sei sicuro? [y/N]: ").strip().lower()
        if confirm != "y":
            logger.info("Operazione annullata.")
            return

    try:
        cleanup_directory(folder, settings=settings)
        logger.info("✅ Pulizia completata.")
    except CleanupError as e:
        logger.error(f"Errore: {e}")
        exit(1)


if __name__ == "__main__":
    cli_cleanup()
