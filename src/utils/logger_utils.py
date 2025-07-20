import logging
import os

def get_logger(name="default", log_file=None, level=logging.INFO):
    """
    Crea un logger con output su console e, se specificato, su file.
    Supporta caratteri Unicode (emoji inclusi).
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Evita duplicazioni se già esiste
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler (con UTF-8)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
