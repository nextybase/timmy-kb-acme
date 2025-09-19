# src/pipeline/env_utils.py
"""Utilità per la gestione dell'ambiente (.env/processo) nella pipeline Timmy-KB.

Cosa fa questo modulo (ruoli e funzioni principali):
- Caricamento `.env` dalla root del progetto (se presente).
- API PURE e prevedibili per leggere variabili:
  - `get_env_var(key, default=None, required=False)` → str|None
  - `require_env(key)` → str (obbligatoria)
  - `get_bool(key, default=False)` → bool (truthy robusto)
  - `get_int(key, default=None, *, required=False, min_value=None, max_value=None)` → int|None
- Flag di redazione log (SSoT):
  - `compute_redact_flag(env, log_level="INFO")` → bool
    Modalità: LOG_REDACTION in {on/off/always/never/auto}; auto abilita se ENV∈{prod,production,ci}
    oppure CI=true oppure sono presenti credenziali sensibili. In DEBUG la redazione è forzata OFF.
- Governance force-push:
  - `get_force_allowed_branches(context=None)` → list[str]
  - `is_branch_allowed_for_force(branch, context=None, *, allow_if_unset=True)` → bool

Linee guida:
- Nessun I/O distruttivo (solo lettura `.env` + `os.environ`).
- Nessun logging qui: gli orchestratori/adapter gestiscono il reporting.
- Coerenza con il domain error handling: alza `ConfigError` per variabili obbligatorie.
"""
from __future__ import annotations

import fnmatch  # per matching glob dei branch
import os
from pathlib import Path
from typing import Any, Mapping, Optional

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
    """Recupera una variabile d'ambiente.

    Args:
        key: nome della variabile.
        default: valore di default se assente/vuota.
        required: se True, solleva ConfigError quando la variabile è assente o vuota.

    Restituisce:
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
#  Helpers interni non esportati
# ================================


def _val_from(env: Mapping[str, Any] | None, key: str, fallback: Optional[str] = None) -> Optional[str]:
    """Legge prima da `env` (se dict-like), poi da `os.environ`."""
    if env is not None and isinstance(env, Mapping) and key in env:
        v = env.get(key)
        return None if v is None else str(v)
    return os.getenv(key, fallback)


def _has_sensitive_credentials(env: Mapping[str, Any] | None) -> bool:
    """True se sono presenti credenziali/percorsi sensibili che suggeriscono redazione log."""
    keys = (
        "GITHUB_TOKEN",
        "SERVICE_ACCOUNT_FILE",
        "GOOGLE_APPLICATION_CREDENTIALS",
    )
    for k in keys:
        if (_val_from(env, k) or "").strip():
            return True
    return False


def _truthy(val: Any) -> bool:
    return str(val).strip().lower() in _TRUE_SET if val is not None else False


# ================================
# Policy redazione (SSoT del flag)
# ================================


def compute_redact_flag(env: Mapping[str, Any] | None, log_level: str = "INFO") -> bool:
    """Calcola il flag di redazione log in modo deterministico (nessun masking qui).

    Regole:
    - LOG_REDACTION=on/always/true  → redazione ON
    - LOG_REDACTION=off/never/false → redazione OFF
    - LOG_REDACTION=auto (default):
        ON se
          * ENV ∈ {prod, production, ci}  OR
          * CI=true                       OR
          * sono presenti credenziali sensibili (es. token/credenziali GCP/GitHub)
        OFF altrimenti
    - log_level=DEBUG forza OFF.
    """
    mode = (_val_from(env, "LOG_REDACTION", "auto") or "auto").strip().lower()

    explicit: Optional[bool]
    if mode in ("always", "on") or mode in _TRUE_SET:
        explicit = True
    elif mode in ("never", "off") or mode in _FALSE_SET:
        explicit = False
    else:
        explicit = None  # auto

    env_name = (_val_from(env, "ENV", "dev") or "dev").strip().lower()
    ci_val = _val_from(env, "CI", "0")
    auto_on = (env_name in {"prod", "production", "ci"}) or _truthy(ci_val) or _has_sensitive_credentials(env)

    redact = explicit if explicit is not None else auto_on

    if str(log_level or "").upper() == "DEBUG":
        return False
    return bool(redact)


# ================================
# Force-push branch allowlist
# ================================


def get_force_allowed_branches(context: Any | None = None) -> list[str]:
    """Legge l'allow-list dei branch per il force push dalla variabile:
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


def is_branch_allowed_for_force(branch: str, context: Any | None = None, *, allow_if_unset: bool = True) -> bool:
    """Verifica se `branch` è consentito per il force push.

    Restituisce:
        True se almeno un pattern combacia (fnmatch), altrimenti False.
        Se la allow-list non è impostata/è vuota → `allow_if_unset`.
    """
    patterns = get_force_allowed_branches(context)
    if not patterns:
        return allow_if_unset
    return any(fnmatch.fnmatch(branch, pat) for pat in patterns)
