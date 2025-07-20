# src/ingest/cleanup.py

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def cleanup_output(config: dict):
    """
    Rimuove in modo sicuro il contenuto della cartella di output Markdown,
    mantenendo la repo .git intatta se esiste.
    """
    output_template = config.get("OUTPUT_DIR_TEMPLATE") or os.getenv("OUTPUT_DIR_TEMPLATE")
    if not output_template:
        logger.error("❌ OUTPUT_DIR_TEMPLATE mancante in config e .env")
        return

    try:
        output_path = Path(output_template.format(**config))
    except KeyError as e:
        logger.error(f"❌ Variabile mancante nel template OUTPUT_DIR_TEMPLATE: {e}")
        return

    if not output_path.exists():
        logger.warning(f"⚠️ Cartella output non trovata: {output_path}")
        return

    confirm = input(f"❓ Vuoi svuotare il contenuto della cartella {output_path}? [y/N] ").strip().lower()
    if confirm != "y":
        logger.info("⏩ Pulizia annullata.")
        return

    try:
        for item in output_path.iterdir():
            if item.name == ".git":
                continue  # 🔒 Manteniamo il repo Git se esiste
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception as inner_e:
                logger.warning(f"⚠️ Impossibile rimuovere {item}: {inner_e}")
        logger.info(f"🧹 Contenuto della cartella {output_path} rimosso.")
    except Exception as e:
        logger.error(f"❌ Errore durante la pulizia: {e}")
