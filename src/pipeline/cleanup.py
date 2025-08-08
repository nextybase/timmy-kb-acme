"""
cleanup.py

Utility di pulizia sicura delle cartelle di output per pipeline Timmy-KB.
Permette di svuotare il contenuto di una directory (file e sottocartelle),
ma protegge root, home e directory critiche.
Utilizzabile sia da pipeline/orchestratori che da CLI (--force).
"""

import shutil
import argparse
from pathlib import Path
from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import get_settings_for_slug  # <-- rimosso import diretto settings

logger = get_structured_logger("pipeline.cleanup")


def _resolve_settings(settings=None):
    """
    Restituisce un'istanza Settings.
    Se non viene passato, prova a usare get_settings_for_slug().
    """
    if settings is None:
        return get_settings_for_slug()
    return settings


def cleanup_output_folder(folder_path, settings=None):
    """
    Svuota tutto il contenuto della cartella specificata (file e sottocartelle),
    lasciando intatta la cartella stessa.

    Args:
        folder_path (str | Path): Percorso della cartella da svuotare.
        settings: Istanza Settings (opzionale, per compatibilità).

    Raises:
        ValueError: Se si tenta di pulire la root del progetto.
    """
    folder = Path(folder_path).resolve()
    # Sicurezza: mai permettere "." o la root del progetto
    if str(folder) in {str(Path().resolve()), str(Path.cwd().resolve())}:
        logger.error("🚫 Tentativo di pulire la root del progetto: operazione bloccata.")
        raise ValueError("Tentativo di pulire la root del progetto!")

    if not folder.exists():
        logger.info(f"La cartella {folder} non esiste, niente da pulire.")
        return

    for item in folder.iterdir():
        if item.is_dir():
            try:
                shutil.rmtree(item)
                logger.info(f"🗑️ Rimossa sottocartella: {item}")
            except Exception as e:
                logger.warning(f"⚠️ Impossibile rimuovere {item}: {e}")
        else:
            try:
                item.unlink()
                logger.info(f"🗑️ Rimosso file: {item}")
            except Exception as e:
                logger.warning(f"⚠️ Impossibile rimuovere {item}: {e}")


def safe_clean_dir(folder_path, settings=None):
    """
    Cancella tutto il contenuto della cartella in modo sicuro.
    Blocca su cartelle critiche (root, home, ecc.).

    Args:
        folder_path (str | Path): Percorso della cartella da svuotare.
        settings: Istanza Settings (opzionale).
    """
    folder = Path(folder_path).resolve()
    forbidden = [Path('/').resolve(), Path.home().resolve(), Path.cwd().root]
    if any(str(folder) == str(fb) for fb in forbidden) or len(str(folder)) < 6:
        logger.error(f"🚫 Tentativo di cancellare directory critica: {folder}")
        raise ValueError("Tentativo di cancellare una directory critica, operazione bloccata.")

    if not folder.exists():
        logger.info(f"La cartella {folder} non esiste, nessuna azione necessaria.")
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
    Modalità CLI interattiva: richiede all'utente il percorso della cartella,
    mostra avviso e richiede conferma prima di procedere.
    """
    settings = _resolve_settings(settings)
    print("\n[Timmy-KB] Pulizia cartella di output")
    default_folder = str(settings.output_dir)
    folder = input(f"Inserisci il percorso della cartella da svuotare [default: {default_folder}]: ").strip()
    if not folder:
        folder = default_folder
    print(f"Stai per svuotare tutto il contenuto di: {folder}")
    confirm = input("Sei sicuro? [y/N]: ").strip().lower()
    if confirm == "y":
        try:
            cleanup_output_folder(folder, settings=settings)
            print("Pulizia completata.")
        except Exception as e:
            print(f"Errore: {e}")
    else:
        print("Operazione annullata.")


def cli_cleanup():
    """
    Entry-point CLI: parsing argomenti, conferma, chiama cleanup_output_folder().
    --folder (str): Cartella da svuotare (default = settings.output_dir).
    --force (flag): Non chiedere conferma.
    """
    parser = argparse.ArgumentParser(
        description="Svuota tutto il contenuto di una cartella di output in modo sicuro.",
        epilog="Esempio: python cleanup.py --folder output/timmy-kb-dummy/ --force"
    )
    parser.add_argument("--folder", type=str, help="Percorso della cartella da svuotare (default: settings.output_dir)")
    parser.add_argument("--force", action="store_true", help="Non chiedere conferma (modalità automatica/pipeline)")
    args = parser.parse_args()

    settings = _resolve_settings()
    folder = args.folder or str(settings.output_dir)

    if not args.force:
        print(f"Attenzione: stai per svuotare tutto il contenuto di: {folder}")
        confirm = input("Sei sicuro? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Operazione annullata.")
            return

    try:
        cleanup_output_folder(folder, settings=settings)
        print("Pulizia completata.")
    except Exception as e:
        print(f"Errore: {e}")
        exit(1)


if __name__ == "__main__":
    cli_cleanup()
