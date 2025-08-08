"""
cleanup.py

Utility di pulizia sicura delle cartelle di output della pipeline Timmy-KB.
Permette di svuotare in sicurezza il contenuto di una directory (file e sottocartelle),
ma protegge root, home e directory critiche.

Modifiche Fase 2:
- Validazione path con _validate_path_in_base_dir
- Uso costanti da constants.py
- Eccezioni uniformi (CleanupError)
- Logger e messaggi coerenti
"""

import shutil
import argparse
from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME
from pipeline.exceptions import CleanupError
from pipeline.utils import _validate_path_in_base_dir

logger = get_structured_logger("pipeline.cleanup")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    """
    return settings or get_settings_for_slug()


def cleanup_output_folder(folder_path, settings=None):
    """
    Svuota in sicurezza il contenuto della cartella specificata (file e sottocartelle),
    lasciando intatta la cartella stessa.
    """
    settings = _resolve_settings(settings)
    folder = Path(folder_path).resolve()

    # Validazione path
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


def safe_clean_dir(folder_path, settings=None):
    """
    Cancella tutto il contenuto della cartella in modo sicuro.
    Blocca path critici come root, home, ecc.
    """
    settings = _resolve_settings(settings)
    folder = Path(folder_path).resolve()

    # Validazione path
    try:
        _validate_path_in_base_dir(folder, settings.base_dir)
    except ValueError as e:
        logger.error(f"❌ Tentativo di cancellare directory critica: {folder}")
        raise CleanupError(f"Tentativo di cancellare directory critica: {folder}") from e

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


def interactive_cleanup(settings=None):
    """
    Modalità CLI interattiva: chiede all’utente conferma per cancellare l’output_dir.
    """
    settings = _resolve_settings(settings)
    print("\n[Timmy-KB] Pulizia cartella di output")

    default_folder = str(settings.output_dir)
    folder = input(f"Inserisci il percorso della cartella da svuotare [default: {default_folder}]: ").strip()
    if not folder:
        folder = default_folder

    print(f"Stai per svuotare: {folder}")
    confirm = input("Sei sicuro? [y/N]: ").strip().lower()
    if confirm == "y":
        try:
            cleanup_output_folder(folder, settings=settings)
            print("Pulizia completata.")
        except CleanupError as e:
            print(f"Errore: {e}")
    else:
        print("Operazione annullata.")


def cli_cleanup():
    """
    Entry-point CLI: parsing argomenti e chiamata cleanup_output_folder().
    """
    parser = argparse.ArgumentParser(
        description="Svuota il contenuto di una cartella di output in modo sicuro.",
        epilog="Esempio: python cleanup.py --folder output/timmy-kb-dummy/ --force"
    )
    parser.add_argument("--folder", type=str, help="Percorso della cartella da svuotare (default: settings.output_dir)")
    parser.add_argument("--force", action="store_true", help="Esegue senza chiedere conferma")

    args = parser.parse_args()
    settings = _resolve_settings()

    folder = args.folder or str(settings.output_dir)
    if not args.force:
        print(f"Attenzione: stai per svuotare {folder}")
        confirm = input("Sei sicuro? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Operazione annullata.")
            return

    try:
        cleanup_output_folder(folder, settings=settings)
        print("Pulizia completata.")
    except CleanupError as e:
        print(f"Errore: {e}")
        exit(1)


if __name__ == "__main__":
    cli_cleanup()
