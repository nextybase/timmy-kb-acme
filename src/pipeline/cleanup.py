from pathlib import Path
import os
import shutil
from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import CleanupError  # custom exception

logger = get_structured_logger("pipeline.cleanup")

def cleanup_output_folder(config: dict) -> bool:
    """
    Rimuove in modo sicuro il contenuto della cartella di output Markdown,
    mantenendo la repo .git intatta se esiste.
    Chiede conferma solo se sono presenti file/cartelle diverse da 'config'.
    Restituisce True se la pulizia è stata eseguita, False se annullata o non necessaria.

    Solleva CleanupError su errore bloccante (es. variabile mancante, permessi, errore rimozione file).
    """
    output_path = Path(config.get("output_path", ""))
    if not output_path or not output_path.exists():
        logger.warning(f"⚠️ Cartella output {output_path} non esistente. Nessuna pulizia necessaria.")
        return False

    items_to_check = [item for item in output_path.iterdir() if item.name != "config"]

    if not items_to_check:
        logger.info(f"🟢 Solo cartella 'config' presente (o output vuota), nessuna pulizia necessaria.")
        return False

    confirm = input(f"❓ Vuoi svuotare il contenuto della cartella {output_path} (eccetto config)? [y/N] ").strip().lower()
    if confirm != "y":
        logger.info("⏹️ Pulizia annullata dall’utente.")
        return False

    try:
        for item in items_to_check:
            if item.name == ".git":
                continue  # 🔒 Manteniamo la repo Git se esiste (safe!)
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception as inner_e:
                logger.warning(f"⚠️ Impossibile rimuovere {item}: {inner_e}")
                raise CleanupError(f"Impossibile rimuovere {item}: {inner_e}")
        logger.info(f"🧹 Contenuto della cartella {output_path} rimosso (config preservata).")
        return True
    except Exception as e:
        logger.error(f"❌ Errore durante la pulizia: {e}")
        raise CleanupError(f"Errore durante la pulizia: {e}")

def safe_remove_dir(path):
    """
    Rimuove ricorsivamente una directory anche se alcuni file sono temporaneamente in uso (Windows-safe).
    Usa retry e delay. Solleva CleanupError se dopo vari tentativi la directory persiste.
    """
    import time
    path = Path(path)
    if not path.exists():
        logger.info(f"🟢 La directory {path} non esiste già (nessuna azione richiesta).")
        return
    for _ in range(5):
        try:
            shutil.rmtree(path, ignore_errors=False)
            logger.info(f"🧹 Directory rimossa: {path}")
            return
        except PermissionError as e:
            logger.warning(f"⚠️ Directory lockata (in uso): {path}. Retry tra poco...")
            time.sleep(0.5)
    logger.error(f"❌ Non riesco a cancellare la directory dopo più tentativi: {path}")
    raise CleanupError(f"Impossibile cancellare la directory: {path}")
