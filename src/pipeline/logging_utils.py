import logging
import os

def get_structured_logger(name="default", log_file=None, level=None):
    """
    Logger strutturato con supporto configurazione via .env (TimmySecrets).
    Importa TimmySecrets localmente per evitare import circolari.
    """
    logger = logging.getLogger(name)

    # Evita duplicazioni
    if logger.handlers:
        return logger

    # Import locale per evitare import circolari
    try:
        from pipeline.config_utils import TimmySecrets
        secrets = TimmySecrets()
        if log_file is None:
            log_file = secrets.log_file_path
        if level is None:
            if secrets.log_level and secrets.log_level.upper() == "DEBUG":
                level = logging.DEBUG
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
            print(f"⚠️ Impossibile scrivere log su file: {log_file} – {e}")

    return logger
