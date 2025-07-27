# pipeline/cleanup.py

import shutil
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
