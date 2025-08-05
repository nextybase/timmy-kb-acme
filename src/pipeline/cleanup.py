# pipeline/cleanup.py

import shutil
import argparse
from pathlib import Path
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.cleanup")


def cleanup_output_folder(folder_path):
    """
    Svuota tutto il contenuto della cartella specificata (file e sottocartelle),
    lasciando intatta la cartella stessa.
    """
    folder = Path(folder_path).resolve()
    # Sicurezza: mai permettere "." o la root del progetto!
    if str(folder) in {str(Path().resolve()), str(Path.cwd().resolve())}:
        logger.error("🚨 Tentativo di pulire la root del progetto: operazione bloccata.")
        raise ValueError("Tentativo di pulire la root del progetto!")

    if not folder.exists():
        logger.info(f"Cartella {folder} non esistente, niente da pulire.")
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


def safe_clean_dir(folder_path):
    """
    Cancella tutto il contenuto della cartella in modo sicuro.
    Bloccato su cartelle critiche (root, home, etc).
    """
    folder = Path(folder_path).resolve()
    forbidden = [Path('/').resolve(), Path.home().resolve(), Path.cwd().root]
    # Anche: blocca se il path è molto corto, tipo /, C:\, ecc.
    if any(str(folder) == str(fb) for fb in forbidden) or len(str(folder)) < 6:
        logger.error(f"🚨 Tentativo di cancellare directory critica: {folder}")
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


def interactive_cleanup():
    print("\n[Timmy-KB] Pulizia cartella di output")
    folder = input("Inserisci il percorso della cartella da svuotare: ").strip()
    if not folder:
        print("Percorso non valido. Operazione annullata.")
        return
    print(f"Stai per svuotare tutto il contenuto di: {folder}")
    confirm = input("Sei sicuro? [y/N]: ").strip().lower()
    if confirm == "y":
        try:
            cleanup_output_folder(folder)
            print("Pulizia completata.")
        except Exception as e:
            print(f"Errore: {e}")
    else:
        print("Operazione annullata.")


def cli_cleanup():
    parser = argparse.ArgumentParser(
        description="Svuota tutto il contenuto di una cartella di output in modo sicuro.",
        epilog="Esempio: python cleanup.py --folder output/timmy-kb-dummy/ --force"
    )
    parser.add_argument("--folder", type=str, help="Percorso della cartella da svuotare")
    parser.add_argument("--force", action="store_true", help="Non chiedere conferma (modalità automatica/pipeline)")
    args = parser.parse_args()

    if not args.folder:
        # Fallback alla modalità interattiva se non specificato da CLI
        interactive_cleanup()
        return

    if not args.force:
        print(f"Attenzione: stai per svuotare tutto il contenuto di: {args.folder}")
        confirm = input("Sei sicuro? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Operazione annullata.")
            return

    try:
        cleanup_output_folder(args.folder)
        print("Pulizia completata.")
    except Exception as e:
        print(f"Errore: {e}")
        exit(1)


if __name__ == "__main__":
    cli_cleanup()
