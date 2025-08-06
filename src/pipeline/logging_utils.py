"""
logging_utils.py

Utility per la creazione di logger strutturati per la pipeline Timmy-KB.
Supporta configurazione via settings centralizzato, logging su file e console,
formattazione uniforme e safe fallback in caso di errori su file handler.
"""

import logging
import os

def get_structured_logger(name="default", log_file=None, level=None):
    """
    Crea un logger strutturato con supporto a configurazione via settings centralizzato.
    Evita duplicazione handler; importa settings localmente per evitare import circolari.

    - Se il logger esiste già (handler presente), restituisce il logger esistente.
    - Supporta logging su file se specificato, altrimenti solo console.

    Args:
        name (str, optional): Nome del logger (default "default").
        log_file (str, optional): Path file di log (default: da settings o None).
        level (int, optional): Livello logging (default: INFO o da settings).

    Returns:
        logging.Logger: Logger configurato secondo le regole pipeline.

    Raises:
        Nessuna: fallback silenzioso se settings/log_file non disponibili.
    """
    logger = logging.getLogger(name)

    # Evita duplicazioni handler
    if logger.handlers:
        return logger

    # Import locale per evitare import circolari
    try:
        from pipeline.config_utils import settings
        if log_file is None:
            log_file = getattr(settings, "logs_path", None)
        if level is None:
            log_level_str = getattr(settings, "log_level", "INFO").upper()
            if log_level_str == "DEBUG":
                level = logging.DEBUG
            elif log_level_str == "WARNING":
                level = logging.WARNING
            elif log_level_str == "ERROR":
                level = logging.ERROR
            else:
                level = logging.INFO
    except Exception:
        level = logging.INFO

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            # Usa direttamente il logger appena configurato per loggare su console!
            logger.warning(f"⚠️ Impossibile scrivere log su file: {log_file} — {e}")

    return logger
