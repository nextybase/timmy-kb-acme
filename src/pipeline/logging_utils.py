import logging
import os

def get_structured_logger(name="default", log_file=None, level=logging.INFO):
    """
    Restituisce un logger strutturato con output su console e, opzionalmente, su file.
    - Formato: timestamp, livello, nome modulo, messaggio (emoji supportate).
    - Su più chiamate/istanze, evita duplicazioni degli handler.
    - Utile sia per debug che per produzione (puoi personalizzare il livello).
    
    Args:
        name (str): Nome del logger (tipicamente il modulo)
        log_file (str): Path file di log (opzionale)
        level (int): Livello log (logging.INFO di default)

    Returns:
        logging.Logger: Oggetto logger pronto all'uso
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Evita duplicazione handler (utile in ambienti notebook o reload multipli)
    if any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
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
