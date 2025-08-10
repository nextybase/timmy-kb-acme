"""
Gestione centralizzata delle variabili di ambiente per Timmy-KB.
Carica automaticamente il file .env nella root del progetto.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carica .env dalla root del progetto
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

def get_env_var(key: str, default=None, required: bool = False):
    """
    Ritorna il valore di una variabile di ambiente.
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise EnvironmentError(f"Variabile di ambiente '{key}' mancante e richiesta")
    return value
