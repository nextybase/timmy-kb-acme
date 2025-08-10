"""
logging_utils.py

Utility per la creazione di logger strutturati per la pipeline Timmy-KB.
Supporta configurazione via settings centralizzato, logging su file e console,
formattazione uniforme e validazione sicura del percorso file log.
"""

import logging
import os
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

from pipeline.constants import LOGS_DIR_NAME
from pipeline.exceptions import PipelineError


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Path] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3
) -> logging.Logger:
    """
    Crea un logger strutturato con supporto a file e console.

    Args:
        name (str): Nome del logger.
        log_file (Optional[Path]): Path file log. Se None, tenta di usare settings.logs_path.
        level (Optional[int]): Livello logging. Se None, tenta di usare settings.LOG_LEVEL.
        rotate (bool): Abilita RotatingFileHandler.
        max_bytes (int): Dimensione massima file log.
        backup_count (int): Numero massimo file di backup.

    Returns:
        logging.Logger: Logger configurato.
    """
    logger = logging.getLogger(name)

    # Evita handler duplicati
    if logger.hasHandlers():
        logger.handlers.clear()

    # Import settings in modo dinamico per evitare cicli
    try:
        from pipeline.config_utils import settings, _validate_path_in_base_dir
        if log_file is None:
            log_file = getattr(settings, "logs_path", None)
        if level is None:
            level_str = getattr(settings, "LOG_LEVEL", "INFO").upper()
            level = getattr(logging, level_str, logging.INFO)
    except Exception:
        if level is None:
            level = logging.INFO
        _validate_path_in_base_dir = None  # fallback

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler (opzionale)
    if log_file:
        try:
            if _validate_path_in_base_dir:
                base_dir = getattr(settings, "base_dir", Path.cwd())
                _validate_path_in_base_dir(Path(log_file), base_dir)

            os.makedirs(Path(log_file).parent, exist_ok=True)

            if rotate:
                fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
            else:
                fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except PipelineError as e:
            logger.warning(f"Percorso log non consentito: {e}. Logging solo su console.")
        except Exception as e:
            logger.warning(f"Impossibile creare file log {log_file}: {e}. Logging solo su console.")

    return logger
