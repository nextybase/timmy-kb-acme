# src/pipeline/env_utils.py

"""
Gestione centralizzata delle variabili di ambiente per Timmy-KB.
Carica automaticamente il file .env nella root del progetto.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from .exceptions import ConfigError  # ⬅️ allineamento eccezioni

# Carica .env dalla root del progetto
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

def get_env_var(key: str, default=None, required: bool = False):
    """
    Ritorna il valore di una variabile di ambiente.

    Args:
        key (str): nome della variabile di ambiente.
        default: valore di default se non presente (usato solo se required=False).
        required (bool): se True, solleva errore se assente.

    Raises:
        ConfigError: se required=True e la variabile non è impostata.

    Returns:
        str | Any: il valore della variabile, o il default se consentito.
    """
    value = os.getenv(key, default)
    if required and value is None:
        # Coerenza con l’error handling della pipeline
        raise ConfigError(f"Variabile di ambiente '{key}' mancante e richiesta")
    return value
