# src/pipeline/logging_utils.py

"""
Utility per la creazione di logger strutturati per la pipeline Timmy-KB.
Supporta configurazione via settings centralizzato o ClientContext,
logging su file e console, formattazione uniforme e validazione sicura
del percorso file log.
"""

import logging
from pathlib import Path
from typing import Optional, Union
from logging.handlers import RotatingFileHandler


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Union[str, Path]] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    context: Optional[object] = None
) -> logging.Logger:
    """
    Crea un logger strutturato con supporto per console e file, opzionalmente
    legato ad un ClientContext (o qualunque oggetto con attributo `.slug`).

    Args:
        name: Nome del logger.
        log_file: Path del file di log. Se None, solo console.
        level: Livello logging (default: INFO).
        rotate: Abilita RotatingFileHandler.
        max_bytes: Dimensione massima file log per rotazione.
        backup_count: Numero massimo file di backup.
        context: (opzionale) Oggetto con attributo `.slug` da associare nei log.

    Returns:
        logging.Logger: Logger configurato.
    """
    logger = logging.getLogger(name)

    # Evita handler duplicati
    if logger.hasHandlers():
        logger.handlers.clear()

    # Livello di default
    if level is None:
        level = logging.INFO
    logger.setLevel(level)

    # Importante: non propagare al root logger per evitare doppie emissioni
    logger.propagate = False

    # Formatter uniforme
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s"
        + (" | slug=%(slug)s" if context else "")
        + " | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    if context:
        ch.addFilter(lambda record: setattr(record, "slug", getattr(context, "slug", "n/a")) or True)
    logger.addHandler(ch)

    # Handler file, se richiesto
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if rotate:
                fh = RotatingFileHandler(
                    log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
                )
            else:
                fh = logging.FileHandler(log_file_path, encoding="utf-8")
            fh.setFormatter(formatter)
            if context:
                fh.addFilter(lambda record: setattr(record, "slug", getattr(context, "slug", "n/a")) or True)
            logger.addHandler(fh)
        except Exception as e:
            # Se il file non è creabile, degrada elegantemente a console-only
            logger.warning(f"Impossibile creare file di log {log_file_path}: {e}. Logging solo su console.")

    return logger
