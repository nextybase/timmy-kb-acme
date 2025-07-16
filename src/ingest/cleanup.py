# utils/cleanup.py

import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def preview_and_cleanup(md_output_path: Path):
    md_output_path = Path(md_output_path)
    md_files = sorted(md_output_path.glob("*.md"))

    if not md_files:
        logger.warning("⚠️ Nessun file Markdown da rivedere.")
        return

    print("\n📝 File Markdown generati:")
    for idx, file in enumerate(md_files, 1):
        print(f"{idx}. {file.name}")

    scelta = input("\nVuoi rimuovere qualche file? (y/n): ").strip().lower()
    if scelta == "y":
        da_cancellare = input("Inserisci i numeri separati da virgola (es: 1,3,5) oppure 'all' per cancellare tutto: ").strip()
        try:
            if da_cancellare == "all":
                for file in md_files:
                    logger.info(f"🗑️  Cancello: {file.name}")
                    file.unlink()
            else:
                indices = [int(i) for i in da_cancellare.split(",")]
                for i in indices:
                    if 1 <= i <= len(md_files):
                        logger.info(f"🗑️  Cancello: {md_files[i-1].name}")
                        md_files[i-1].unlink()
        except Exception as e:
            logger.error(f"❌ Errore nella cancellazione: {e}")
    else:
        logger.info("✅ Nessun file è stato rimosso.")
