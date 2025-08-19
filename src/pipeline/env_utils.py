# src/pipeline/env_utils.py

"""
Utility per la gestione delle variabili d'ambiente.

- Carica automaticamente il file .env nella root del progetto (se presente).
- Mantiene la funzione legacy `get_env_var(...)` per retro-compatibilità.
- **Linee guida**: usare SEMPRE queste funzioni al posto di `os.getenv` nei moduli.
- Aggiunge utility tipizzate e sicure:
    - require_env(key): stringa obbligatoria (vuoto = errore)
    - get_bool(key, default=False): parsing booleano tollerante
    - get_int(key, default=None, required=False): intero con validazione
    - redact_secrets(text): redazione di token/segreti nei messaggi/log
    - is_log_redaction_enabled(context): toggle centralizzato per la redazione log
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from .exceptions import ConfigError  # coerenza con l'error handling della pipeline

# Carica .env dalla root del progetto
# Struttura attesa: <repo_root>/src/pipeline/env_utils.py → parents[2] = <repo_root>
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

__all__ = [
    "get_env_var",
    "require_env",
    "get_bool",
    "get_int",
    "redact_secrets",
    "is_log_redaction_enabled",
]

def get_env_var(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Recupera una variabile d'ambiente con comportamento retro-compatibile.

    Uso raccomandato in TUTTI i moduli al posto di `os.getenv`, per centralizzare:
    - default e gestione 'required'
    - messaggistica coerente con la pipeline

    Args:
        key: nome della variabile d'ambiente
        default: valore di fallback se la variabile non è presente
        required: se True, solleva ConfigError quando la variabile è assente **o vuota**

    Returns:
        Il valore della variabile o il default (None o stringa).

    Raises:
        ConfigError: se required=True e la variabile è assente o vuota
    """
    value = os.getenv(key, default)
    if required and (value is None or str(value).strip() == ""):
        # Coerenza con l’error handling della pipeline e con require_env()
        raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
    return value


# -----------------------------
#  👇 Nuove utility non-breaking
# -----------------------------

_TRUE_SET = {"1", "true", "yes", "on", "y", "t"}

def require_env(key: str) -> str:
    """
    Versione 'required' esplicita.
    Considera stringa vuota ('') come mancante.

    Raises:
        ConfigError: se la variabile è assente o vuota
    """
    val = os.getenv(key)
    if val is None or str(val).strip() == "":
        raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
    return val


def get_bool(key: str, default: bool = False) -> bool:
    """
    Lettura booleana tollerante.
    True se il valore (case-insensitive) ∈ {_TRUE_SET}, altrimenti:
      - False se non presente
      - default per valori non riconosciuti
    """
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in _TRUE_SET


def get_int(key: str, default: Optional[int] = None, *, required: bool = False) -> Optional[int]:
    """
    Lettura intera con validazione minima.

    Args:
        key: nome della variabile
        default: valore di fallback se assente/non valido
        required: se True, solleva ConfigError se assente/vuota/non numerica

    Returns:
        int o default/None

    Raises:
        ConfigError: se required=True e la variabile è assente/vuota/non numerica
    """
    v = os.getenv(key, None)
    if v is None or str(v).strip() == "":
        if required:
            raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        if required:
            raise ConfigError(f"Variabile di ambiente '{key}' non numerica: {v!r}")
        return default


# Elenco chiavi comunemente sensibili: estendibile senza side-effect
_SECRET_KEYS = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "PAT",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
)

def redact_secrets(text: str) -> str:
    """
    Maschera nei messaggi eventuali token/segreti presenti nell'ambiente.
    Utile per logging di errori/traceback senza rischi di leakage.
    """
    if not text:
        return text
    redacted = str(text)
    for k in _SECRET_KEYS:
        v = os.getenv(k)
        if v:
            redacted = redacted.replace(v, "****")
    return redacted


def is_log_redaction_enabled(context=None) -> bool:
    """
    Determina se la redazione dei log deve essere attiva.

    Logica:
      - LOG_REDACTION=always  → True
      - LOG_REDACTION=never   → False
      - LOG_REDACTION in {1,true,yes,on} → True
      - LOG_REDACTION in {0,false,no,off} → False
      - LOG_REDACTION=auto (default): True se ENV ∈ {prod, production}, altrimenti False

    La precedenza è: context.env > os.environ.
    """
    def _from_ctx(key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            if context is not None and hasattr(context, "env") and isinstance(context.env, dict):
                return context.env.get(key, default)
        except Exception:
            pass
        return default

    mode = _from_ctx("LOG_REDACTION") or os.getenv("LOG_REDACTION", "auto")
    mode_l = str(mode or "auto").strip().lower()

    if mode_l in ("always",) or mode_l in _TRUE_SET:
        return True
    if mode_l in ("never", "0", "false", "no", "off"):
        return False

    # auto
    envv = _from_ctx("ENV") or os.getenv("ENV", "dev")
    return str(envv).strip().lower() in ("prod", "production")
