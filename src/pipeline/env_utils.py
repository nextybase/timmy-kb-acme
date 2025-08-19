# src/pipeline/env_utils.py
from __future__ import annotations

import os
import fnmatch  # ✅ NEW: per matching glob dei branch
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
    # ✅ NEW:
    "get_force_allowed_branches",
    "is_branch_allowed_for_force",
]

def get_env_var(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Recupera una variabile d'ambiente con comportamento retro-compatibile.
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
    """Versione 'required' esplicita."""
    val = os.getenv(key)
    if val is None or str(val).strip() == "":
        raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
    return val


def get_bool(key: str, default: bool = False) -> bool:
    """Lettura booleana tollerante."""
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in _TRUE_SET


def get_int(key: str, default: Optional[int] = None, *, required: bool = False) -> Optional[int]:
    """Lettura intera con validazione minima."""
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
    Precedenza: context.env > os.environ.
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


# ================================
# ✅ NEW: Force-push branch allowlist
# ================================

def get_force_allowed_branches(context=None) -> list[str]:
    """
    Legge l'allow-list dei branch per il force push dalla variabile:
      GIT_FORCE_ALLOWED_BRANCHES=main,release/*

    - Supporta lista separata da virgole e/o newline.
    - Legge prima da context.env (se presente), poi da os.environ.
    - Ritorna una lista di pattern glob (es. ["main", "release/*"]).
    - Se non impostata o vuota → [] (nessun vincolo lato helper).

    Nota: l’orchestratore può interpretare [] come “nessun filtro” e,
    in tal caso, decidere se consentire tutto o bloccare by-policy.
    """
    raw = None
    try:
        if context is not None and hasattr(context, "env") and isinstance(context.env, dict):
            raw = context.env.get("GIT_FORCE_ALLOWED_BRANCHES", None)
    except Exception:
        raw = None
    if raw is None:
        raw = os.getenv("GIT_FORCE_ALLOWED_BRANCHES", "")

    # Normalizzazione: separatori = virgola o newline
    tokens = str(raw or "").replace("\n", ",").split(",")
    patterns = [t.strip() for t in tokens if t and t.strip()]
    return patterns


def is_branch_allowed_for_force(branch: str, context=None, *, allow_if_unset: bool = True) -> bool:
    """
    Verifica se `branch` è consentito per il force push.

    Args:
        branch: nome del branch (es. "main", "release/1.2.x").
        context: opzionale; se presente può fornire `context.env`.
        allow_if_unset: se True e la lista non è configurata/è vuota → consenti.

    Returns:
        True se almeno un pattern della allow-list combacia (fnmatch), altrimenti False.
        Se la allow-list non è impostata/è vuota → `allow_if_unset`.
    """
    patterns = get_force_allowed_branches(context)
    if not patterns:
        return allow_if_unset
    return any(fnmatch.fnmatch(branch, pat) for pat in patterns)
