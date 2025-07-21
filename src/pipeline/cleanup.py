# src/pipeline/cleanup.py

from pathlib import Path
import os
import shutil
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.cleanup")

def cleanup_output_folder(config: dict) -> bool:
    """
    Rimuove in modo sicuro il contenuto della cartella di output Markdown,
    mantenendo la repo .git intatta se esiste.
    Chiede conferma solo se sono presenti file/cartelle diverse da 'config'.
    Restituisce True se la pulizia è stata eseguita, False se annullata o non necessaria.
    """
    output_template = config.get("OUTPUT_DIR_TEMPLATE") or os.getenv("OUTPUT_DIR_TEMPLATE")
    if not output_template:
        logger.error("❌ OUTPUT_DIR_TEMPLATE mancante in config e .env")
        return False

    try:
        output_path = Path(output_template.format(**config))
    except KeyError as e:
        logger.error(f"❌ Variabile mancante nel template OUTPUT_DIR_TEMPLATE: {e}")
        return False

    if not output_path.exists():
        logger.warning(f"⚠️ Cartella output {output_path} non esistente. Nessuna pulizia necessaria.")
        return False

    # Escludi la sola presenza della cartella 'config'
    items_to_check = [item for item in output_path.iterdir() if item.name != "config"]

    if not items_to_check:
        logger.info(f"🟢 Solo cartella 'config' presente (o output vuota), nessuna pulizia necessaria.")
        return False

    # Chiedi conferma solo se ci sono altri file/cartelle
    confirm = input(f"❓ Vuoi svuotare il contenuto della cartella {output_path} (eccetto config)? [y/N] ").strip().lower()
    if confirm != "y":
        logger.info("⏩ Pulizia annullata dall’utente.")
        return False

    try:
        for item in items_to_check:
            if item.name == ".git":
                continue  # 🔒 Manteniamo il repo Git se esiste
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception as inner_e:
                logger.warning(f"⚠️ Impossibile rimuovere {item}: {inner_e}")
        logger.info(f"🧹 Contenuto della cartella {output_path} rimosso (config preservata).")
        return True
    except Exception as e:
        logger.error(f"❌ Errore durante la pulizia: {e}")
        return False
