# src/pipeline/env_utils.py
from __future__ import annotations

import os
import fnmatch  # per matching glob dei branch
from pathlib import Path
from typing import Optional, Mapping, Any

from dotenv import load_dotenv

from .exceptions import ConfigError  # coerenza con l'error handling della pipeline

# Carica .env dalla root del progetto
# Struttura attesa: <repo_root>/src/pipeline/env_utils.py → parents[2] = <repo_root>
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

__all__ = [
    # API pure e canoniche
    "get_env_var",
    "require_env",
    "get_bool",
    "get_int",
    "compute_redact_flag",
    "get_force_allowed_branches",
    "is_branch_allowed_for_force",
]

# -----------------------------
#  Utility base (PURE)
# -----------------------------

_TRUE_SET = {"1", "true", "yes", "on", "y", "t"}
_FALSE_SET = {"0", "false", "no", "off", "n", "f"}


def get_env_var(
    key: str,
    default: Optional[str] = None,
    required: bool = False,
) -> Optional[str]:
    """
    Recupera una variabile d'ambiente.

    Args:
        key: nome della variabile.
        default: valore di default se assente/vuota.
        required: se True, solleva ConfigError quando la variabile è assente o vuota.

    Returns:
        Il valore (stringa) o `None`.
    """
    value = os.getenv(key, default)
    if required and (value is None or str(value).strip() == ""):
        raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
    return value


def require_env(key: str) -> str:
    """Versione obbligatoria: restituisce sempre una stringa o solleva ConfigError."""
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


def get_int(
    key: str,
    default: Optional[int] = None,
    *,
    required: bool = False,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> Optional[int]:
    """Lettura intera con validazione minima e bounds opzionali."""
    v = os.getenv(key, None)
    if v is None or str(v).strip() == "":
        if required:
            raise ConfigError(f"Variabile di ambiente '{key}' mancante o vuota")
        return default
    try:
        val = int(str(v).strip())
    except (TypeError, ValueError):
        if required:
            raise ConfigError(f"Variabile di ambiente '{key}' non numerica: {v!r}")
        return default

    if min_value is not None and val < min_value:
        if required:
            raise ConfigError(f"Variabile '{key}' fuori range (<{min_value}): {val}")
        return default
    if max_value is not None and val > max_value:
        if required:
            raise ConfigError(f"Variabile '{key}' fuori range (>{max_value}): {val}")
        return default
    return val


# ================================
# Policy redazione (SSoT del flag)
# ================================

def _truthy(val: Any) -> bool:
    return str(val).strip().lower() in _TRUE_SET if val is not None else False


def compute_redact_flag(env: Mapping[str, Any], log_level: str = "INFO") -> bool:
    """
    Calcola il flag di redazione log in modo deterministico (nessun masking qui).

    Regole:
    - LOG_REDACTION=on/always/true  → redazione ON
    - LOG_REDACTION=off/never/false → redazione OFF
    - LOG_REDACTION=auto (default):
        ON se
          * ENV ∈ {prod, production, ci}  OR
          * CI=true                       OR
          * sono presenti credenziali sensibili (GITHUB_TOKEN o SERVICE_ACCOUNT_FILE)
        OFF altrimenti
    - log_level=DEBUG forza OFF.

    Args:
        env: mappa chiave→valore (tipicamente `context.env`).
        log_level: stringa livello log (es. "INFO", "DEBUG").

    Returns:
        True se la redazione va attivata, False altrimenti.
    """
    mode = (env.get("LOG_REDACTION") if env is not None else None) or os.getenv("LOG_REDACTION", "auto")
    mode_l = str(mode or "auto").strip().lower()

    if mode_l in ("always", "on") or mode_l in _TRUE_SET:
        explicit = True
    elif mode_l in ("never", "off") or mode_l in _FALSE_SET:
        explicit = False
    else:
        explicit = None  # auto

    env_name = (env.get("ENV") if env is not None else None) or os.getenv("ENV", "dev")
    ci_val = (env.get("CI") if env is not None else None) or os.getenv("CI", "0")
    has_credentials = bool(
        (env.get("GITHUB_TOKEN") if env is not None else None) or os.getenv("GITHUB_TOKEN") or
        (env.get("SERVICE_ACCOUNT_FILE") if env is not None else None) or os.getenv("SERVICE_ACCOUNT_FILE")
    )

    auto_on = (str(env_name).strip().lower() in {"prod", "production", "ci"}) or _truthy(ci_val) or has_credentials
    redact = explicit if explicit is not None else auto_on

    if str(log_level or "").upper() == "DEBUG":
        return False
    return bool(redact)


# ================================
# Force-push branch allowlist
# ================================

def get_force_allowed_branches(context=None) -> list[str]:
    """
    Legge l'allow-list dei branch per il force push dalla variabile:
      GIT_FORCE_ALLOWED_BRANCHES=main,release/*

    - Supporta lista separata da virgole e/o newline.
    - Precedenza: `context.env` (se presente), poi `os.environ`.
    - Ritorna una lista di pattern glob (es. ["main", "release/*"]).
    - Se non impostata o vuota → [] (nessun vincolo lato helper).
    """
    raw = None
    try:
        if context is not None and hasattr(context, "env") and isinstance(context.env, dict):
            raw = context.env.get("GIT_FORCE_ALLOWED_BRANCHES", None)
    except Exception:
        raw = None
    if raw is None:
        raw = os.getenv("GIT_FORCE_ALLOWED_BRANCHES", "")

    tokens = str(raw or "").replace("\n", ",").split(",")
    patterns = [t.strip() for t in tokens if t and t.strip()]
    return patterns


def is_branch_allowed_for_force(branch: str, context=None, *, allow_if_unset: bool = True) -> bool:
    """
    Verifica se `branch` è consentito per il force push.

    Returns:
        True se almeno un pattern combacia (fnmatch), altrimenti False.
        Se la allow-list non è impostata/è vuota → `allow_if_unset`.
    """
    patterns = get_force_allowed_branches(context)
    if not patterns:
        return allow_if_unset
    return any(fnmatch.fnmatch(branch, pat) for pat in patterns)
