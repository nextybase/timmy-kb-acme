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
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.logging_utils import get_structured_logger

from .exceptions import ConfigError
from .path_utils import read_text_safe

__all__ = [
    "ensure_dotenv_loaded",
    "get_env_var",
    "get_bool",
    "get_int",
    "is_beta_strict",
    "compute_redact_flag",
]

_LOGGER = get_structured_logger("pipeline.env_utils")
_ENV_LOADED = False


def ensure_dotenv_loaded(*, strict: bool = True, allow_fallback: bool = False) -> bool:
    """Carica il file .env una sola volta su richiesta esplicita.

    Ritorna True se il caricamento e stato eseguito in questa chiamata,
    False se gia caricato in precedenza o se `python-dotenv` non e disponibile.
    """
    global _ENV_LOADED
    env_path = Path(".env")
    if _ENV_LOADED:
        try:
            from dotenv import load_dotenv
        except Exception:
            return False
        if not callable(load_dotenv):
            return False
        if getattr(load_dotenv, "__module__", "").startswith("dotenv"):
            return False
        try:
            loaded: Optional[bool] = load_dotenv(override=False)
        except Exception as exc:
            if allow_fallback:
                _LOGGER.warning(
                    "env.load_failed_fallback",
                    extra={"error": str(exc), "path": str(env_path)},
                )
                return False
            raise ConfigError("Caricamento .env fallito.", file_path=str(env_path)) from exc
        _LOGGER.info(
            "env.loaded",
            extra={"loaded": bool(loaded), "path": str(env_path)},
        )
        if not env_path.exists():
            _LOGGER.info("env.dotenv_missing", extra={"path": str(env_path)})
        return False
    _ENV_LOADED = True
    try:
        spec = importlib.util.find_spec("dotenv")
    except Exception:
        spec = None
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None
    if spec is None and not callable(load_dotenv):
        if strict and env_path.exists():
            raise ConfigError("python-dotenv non disponibile ma .env presente", file_path=str(env_path))
        _LOGGER.info(
            "env.dotenv_unavailable",
            extra={"path": str(env_path), "env_exists": env_path.exists()},
        )
        if not env_path.exists():
            _LOGGER.info("env.dotenv_missing", extra={"path": str(env_path)})
        return False
    try:
        if getattr(load_dotenv, "__module__", "").startswith("dotenv"):
            loaded: Optional[bool] = load_dotenv(
                dotenv_path=str(env_path),
                override=False,
            )  # carica da CWD; non forza override
        else:
            loaded = load_dotenv(override=False)
        _LOGGER.info(
            "env.loaded",
            extra={"loaded": bool(loaded), "path": str(env_path)},
        )
        if not env_path.exists():
            _LOGGER.info("env.dotenv_missing", extra={"path": str(env_path)})
        # Caricamento deterministico da .env (senza override) per garantire le variabili.
        if env_path.exists():
            text = read_text_safe(Path.cwd(), env_path, encoding="utf-8")
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
        return True
    except Exception as exc:
        if allow_fallback:
            _LOGGER.warning(
                "env.load_failed_fallback",
                extra={"error": str(exc), "path": str(env_path)},
            )
            return False
        raise ConfigError("Caricamento .env fallito.", file_path=str(env_path)) from exc
    finally:
        # Non ripristiniamo le variabili mancanti: se .env le fornisce, sono necessarie
        # per i flussi reali (Drive/GitHub) e devono rimanere disponibili nel processo.
        pass


def get_env_var(
    name: str,
    default: Optional[str] = None,
    *,
    required: bool | None = False,
    strict: bool = True,
    allow_fallback: bool = False,
) -> Optional[str]:
    """Ritorna il valore di una variabile d'ambiente.

    - Trimma spazi; se vuota, tratta come non impostata.
    - Se ``required`` e non presente, solleva ``ConfigError`` solo in strict.
    """
    strict_load = strict and bool(required)
    ensure_dotenv_loaded(strict=strict_load, allow_fallback=allow_fallback)
    val = os.environ.get(name)
    if val is None:
        if required and strict:
            raise ConfigError(f"ENV missing: {name}")
        return default
    sval = val.strip()
    if sval == "":
        if required and strict:
            raise ConfigError(f"ENV empty: {name}")
        return default
    return sval


def get_bool(
    name: str,
    default: bool = False,
    *,
    env: Mapping[str, str] | None = None,
    strict: bool | None = None,
    allow_fallback: bool = False,
) -> bool:
    """Parsa un booleano da ENV (o mapping fornito) usando valori comuni truthy/falsy.

    Truthy: 1,true,yes,on (case-insensitive). Falsy: 0,false,no,off.
    Se non impostata, ritorna sempre ``default``.
    Se non riconosciuta, solleva `ConfigError` in strict (default su env reale) o
    ritorna `default` solo se `allow_fallback=True` o `strict=False`.
    Passando ``env`` si evita il caricamento di .env ed e possibile usare mapping custom.
    """
    source: Mapping[str, str]
    if env is not None:
        if strict is None:
            strict = False
        source = env
    else:
        if strict is None:
            strict = True
        ensure_dotenv_loaded(strict=False, allow_fallback=allow_fallback)
        source = os.environ
    val = source.get(name)
    if val is None:
        return bool(default)
    s = str(val).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    if allow_fallback:
        return bool(default)
    if strict:
        raise ConfigError(f"ENV invalid boolean: {name}")
    return bool(default)


def get_int(name: str, default: int = 0, *, strict: bool = True, allow_fallback: bool = False) -> int:
    """Parsa un intero da ENV; ritorna `default` se mancante.

    Valore presente ma non valido: solleva `ConfigError` in strict (default),
    oppure ritorna `default` se `allow_fallback=True` o `strict=False`.
    """
    ensure_dotenv_loaded(strict=False, allow_fallback=allow_fallback)
    val = os.environ.get(name)
    if val is None:
        return int(default)
    try:
        return int(str(val).strip())
    except Exception as exc:
        if allow_fallback:
            return int(default)
        if strict:
            raise ConfigError(f"ENV invalid int: {name}", file_path=str(val)) from exc
    return int(default)


def is_beta_strict(env: Mapping[str, str] | None = None) -> bool:
    return get_bool("TIMMY_BETA_STRICT", default=False, env=env, strict=False)


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
