import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def cleanup_output(config: dict):
    """
    Svuota la cartella di output Markdown generata durante la pipeline, 
    solo se è esattamente quella attesa: /output/timmy_kb_<slug>.
    Non tenta più di cancellare l'intera cartella per evitare errori di lock su Windows.
    """
    output_path = config.get("md_output_path")
    slug = config.get("slug")

    if not output_path or not slug:
        logger.warning("⚠️ 'md_output_path' o 'slug' mancante nel config.")
        return

    output_path = Path(output_path)
    expected_path = Path(__file__).resolve().parents[2] / "output" / f"timmy_kb_{slug}"

    if output_path.resolve() != expected_path:
        logger.error(f"❌ Per sicurezza, la cartella '{output_path}' non corrisponde a quella attesa: '{expected_path}'. Operazione annullata.")
        return

    if not output_path.exists():
        logger.info(f"ℹ️ La cartella di output non esiste: {output_path}")
        return

    try:
        risposta = input(f"❓ Vuoi svuotare il contenuto della cartella {output_path}? [y/N] ").strip().lower()
        if risposta == "y":
            for item in output_path.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except Exception as inner_e:
                    logger.warning(f"⚠️ Impossibile rimuovere {item}: {inner_e}")
            logger.info(f"🧹 Contenuto della cartella {output_path} rimosso.")
        else:
            logger.info("🛑 Operazione annullata dall’utente.")
    except Exception as e:
        logger.error(f"❌ Errore durante la pulizia della cartella: {e}")
