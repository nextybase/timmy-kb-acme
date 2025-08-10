# src/pipeline/logging_utils.py
"""
Utility per la creazione di logger strutturati per la pipeline Timmy-KB.
Supporta configurazione via settings centralizzato o ClientContext,
logging su file e console, formattazione uniforme e validazione sicura
del percorso file log.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Union
from logging.handlers import RotatingFileHandler

from pipeline.constants import LOGS_DIR_NAME
from pipeline.exceptions import PipelineError
from pipeline.context import ClientContext


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Union[str, Path]] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    context: Optional[ClientContext] = None
) -> logging.Logger:
    """
    Crea un logger strutturato con supporto per console e file, opzionalmente
    legato ad un ClientContext.

    Args:
        name: Nome del logger.
        log_file: Path del file di log. Se None, solo console.
        level: Livello logging (default: INFO).
        rotate: Abilita RotatingFileHandler.
        max_bytes: Dimensione massima file log per rotazione.
        backup_count: Numero massimo file di backup.
        context: (opzionale) ClientContext per associare automaticamente lo slug nei log.

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
        ch.addFilter(lambda record: setattr(record, "slug", context.slug) or True)
    logger.addHandler(ch)

    # Handler file, se richiesto
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if rotate:
                fh = RotatingFileHandler(log_file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
            else:
                fh = logging.FileHandler(log_file_path, encoding="utf-8")
            fh.setFormatter(formatter)
            if context:
                fh.addFilter(lambda record: setattr(record, "slug", context.slug) or True)
            logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"Impossibile creare file di log {log_file_path}: {e}. Logging solo su console.")

    return logger
