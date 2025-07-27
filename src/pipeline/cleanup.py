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
        logger.error("❌ Tentativo di pulire la root del progetto: operazione bloccata.")
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
