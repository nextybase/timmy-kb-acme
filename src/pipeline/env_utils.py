# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Env utilities senza side-effects a import-time.

Espone:
- ``ensure_dotenv_loaded()``: carica .env on-demand (idempotente).
- ``get_env_var(name, default=None, required=False)``: lettura sicura.
- ``get_bool(name, default=False)``: parsing booleano da ENV.
- ``compute_redact_flag(env, level)``: policy minima per redazione log.
"""

import importlib.util
import os
from collections.abc import Mapping
from typing import Any, Dict, Optional

from pipeline.logging_utils import get_structured_logger

from .path_utils import read_text_safe

__all__ = [
    "ensure_dotenv_loaded",
    "get_env_var",
    "get_bool",
    "get_int",
    "compute_redact_flag",
]

_LOGGER = get_structured_logger("pipeline.env_utils")
_ENV_LOADED = False


def ensure_dotenv_loaded() -> bool:
    """Carica il file .env una sola volta su richiesta esplicita.

    Ritorna True se il caricamento è stato eseguito in questa chiamata,
    False se già caricato in precedenza o se `python-dotenv` non è disponibile.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return False
    if importlib.util.find_spec("dotenv") is None:
        return False
    try:
        from dotenv import load_dotenv

        loaded: Optional[bool] = load_dotenv()  # carica da CWD; non forza override
        _ENV_LOADED = True
        try:
            _LOGGER.info("env.loaded", extra={"loaded": bool(loaded)})
        except Exception:
            pass
        # Fallback minimale: se python-dotenv non ha popolato, prova parse basilare
        try:
            from pathlib import Path as _Path

            env_path = _Path(".env")
            if env_path.exists():
                # Lettura sicura rispetto alla CWD come perimetro
                text = read_text_safe(_Path.cwd(), env_path, encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and os.environ.get(k) is None:
                        os.environ[k] = v
        except Exception:
            pass
        return True
    except Exception:
        # Non propagare: il caricamento .env è best-effort
        return False


def get_env_var(name: str, default: Optional[str] = None, *, required: bool | None = False) -> Optional[str]:
    """Ritorna il valore di una variabile d'ambiente.

    - Trimma spazi; se vuota, tratta come non impostata.
    - Se ``required`` e non presente, solleva ``KeyError``.
    """
    try:
        ensure_dotenv_loaded()
    except Exception:
        # Best-effort: il loader è idempotente e può non essere disponibile
        # (nessuna eccezione propagata)
        pass
    val = os.environ.get(name)
    if val is None:
        if required:
            raise KeyError(f"ENV missing: {name}")
        return default
    sval = val.strip()
    if sval == "":
        if required:
            raise KeyError(f"ENV empty: {name}")
        return default
    return sval


def get_bool(name: str, default: bool = False, *, env: Mapping[str, str] | None = None) -> bool:
    """Parsa un booleano da ENV (o mapping fornito) usando valori comuni truthy/falsy.

    Truthy: 1,true,yes,on (case-insensitive). Falsy: 0,false,no,off.
    Se non impostata o non riconosciuta, ritorna ``default``.
    Passando ``env`` si evita il caricamento di .env ed è possibile usare mapping custom.
    """
    source: Mapping[str, str]
    if env is not None:
        source = env
    else:
        try:
            ensure_dotenv_loaded()
        except Exception:
            pass
        source = os.environ
    val = source.get(name)
    if val is None:
        return bool(default)
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def get_int(name: str, default: int = 0) -> int:
    """Parsa un intero da ENV; ritorna `default` se mancante o non valido."""
    try:
        ensure_dotenv_loaded()
    except Exception:
        pass
    val = os.environ.get(name)
    if val is None:
        return int(default)
    try:
        return int(str(val).strip())
    except Exception:
        return int(default)


def compute_redact_flag(env: Optional[Dict[str, Any]] = None, level: str = "INFO") -> bool:
    """Calcola se redigere i log in base a ENV e livello.

    Policy minimale e non invasiva:
    - Se LOG_REDACTION/LOG_REDACTED truthy -> True.
    - Altrimenti, se ENV ∈ {"prod","production"} -> True.
    - Altrimenti False.
    """
    data = env or dict(os.environ)
    val = str(data.get("LOG_REDACTION") or data.get("LOG_REDACTED") or "").strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    env_name = str(data.get("ENV") or "").strip().lower()
    if env_name in {"prod", "production"}:
        return True
    return False
