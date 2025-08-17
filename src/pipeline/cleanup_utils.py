# src/pipeline/cleanup_utils.py
"""
Utility di pulizia sicura delle cartelle di output della pipeline Timmy-KB.

Consente di svuotare in sicurezza il contenuto di una directory (file e sottocartelle),
lasciando intatta la cartella stessa. Include protezione da path critici (root, home, ecc.).
"""

from __future__ import annotations

import shutil
import argparse
from pathlib import Path

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME
from pipeline.exceptions import CleanupError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # controllo path robusto

logger = get_structured_logger("pipeline.cleanup")


# -------------------------
# Pulizia sicura
# -------------------------
def cleanup_directory(folder_path: Path, context: ClientContext) -> None:
    """Svuota in sicurezza il contenuto della cartella specificata (file e sottocartelle).

    La cartella stessa non viene rimossa.

    Args:
        folder_path: Percorso della cartella da svuotare.
        context: Contesto cliente (per verificare base_dir).

    Raises:
        CleanupError: se il percorso non è sicuro o non validabile.
    """
    folder = Path(folder_path).resolve()

    try:
        base_dir = context.base_dir
        if not is_safe_subpath(folder, base_dir):
            raise CleanupError(f"Tentativo di pulire un path non sicuro: {folder}")
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


# Alias per retrocompatibilità interna (non più usati direttamente)
safe_clean_dir = cleanup_directory
cleanup_output_folder = cleanup_directory


# -------------------------
# Modalità interattiva CLI
# -------------------------
def interactive_cleanup(context: ClientContext) -> None:
    """Modalità CLI interattiva: chiede conferma per cancellare `output_dir` del cliente."""
    default_folder = str(context.output_dir)
    folder = input(f"\n[Timmy-KB] Inserisci il percorso della cartella da svuotare [default: {default_folder}]: ").strip()
    if not folder:
        folder = default_folder

    logger.info(f"Stai per svuotare: {folder}")
    confirm = input("Sei sicuro? [y/N]: ").strip().lower()
    if confirm == "y":
        try:
            cleanup_directory(Path(folder), context)
            logger.info("✅ Pulizia completata.")
        except CleanupError as e:
            logger.error(f"Errore: {e}")
    else:
        logger.info("Operazione annullata.")


# -------------------------
# Entry point CLI
# -------------------------
def cli_cleanup() -> None:
    """Entry-point CLI: parsing argomenti e chiamata a `cleanup_directory()`."""
    parser = argparse.ArgumentParser(
        description="Svuota il contenuto di una cartella di output in modo sicuro.",
        epilog="Esempio: python cleanup_utils.py --slug mio-cliente --folder output/timmy-kb-mio-cliente/"
    )
    parser.add_argument("--folder", type=str, help="Percorso della cartella da svuotare (default: context.output_dir)")
    parser.add_argument("--slug", type=str, required=True, help="Slug cliente per caricare ClientContext")
    parser.add_argument("--force", action="store_true", help="Esegui senza conferma")

    args = parser.parse_args()

    # Caricamento contesto cliente
    context = ClientContext.load(args.slug)

    folder = args.folder or str(context.output_dir)
    if not args.force:
        logger.info(f"Attenzione: stai per svuotare {folder}")
        confirm = input("Sei sicuro? [y/N]: ").strip().lower()
        if confirm != "y":
            logger.info("Operazione annullata.")
            return

    try:
        cleanup_directory(Path(folder), context)
        logger.info("✅ Pulizia completata.")
    except CleanupError as e:
        logger.error(f"Errore: {e}")
        exit(1)


if __name__ == "__main__":
    cli_cleanup()
