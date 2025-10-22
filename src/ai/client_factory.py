# src/ai/client_factory.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from pipeline.exceptions import ConfigError

try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore

    _DOTENV_LOADED = bool(load_dotenv(find_dotenv(usecwd=True), override=False))
    if not _DOTENV_LOADED:
        repo_root = Path(__file__).resolve().parents[2]
        env_path = repo_root / ".env"
        if env_path.exists():
            _DOTENV_LOADED = bool(load_dotenv(env_path, override=False))
except Exception:
    # python-dotenv non installato: l'ambiente deve provvedere alle variabili
    _DOTENV_LOADED = False


def _normalize_base_url(raw: str) -> str:
    base = raw.strip()
    if not base:
        return "https://api.openai.com/v1"
    if "://" not in base:
        base = "https://" + base
    if not base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def make_openai_client():
    """
    Costruisce un client OpenAI (SDK >= 2) applicando le policy del progetto.

    Richiede che `OPENAI_API_KEY` sia impostata.
    Le variabili legacy (`OPENAI_API_KEY_FOLDER`, `OPENAI_FORCE_HTTPX`) non sono più supportate.
    """
    legacy_key = os.getenv("OPENAI_API_KEY_FOLDER")
    api_key = os.getenv("OPENAI_API_KEY")
    if legacy_key and not api_key:
        raise ConfigError(
            "OPENAI_API_KEY_FOLDER non è più supportata. Sposta il valore in OPENAI_API_KEY (.env/ambiente)."
        )
    if not api_key:
        raise ConfigError("Manca la API key. Imposta la variabile di ambiente OPENAI_API_KEY.")

    if _is_truthy(os.getenv("OPENAI_FORCE_HTTPX")):
        raise ConfigError("OPENAI_FORCE_HTTPX non è più supportata: il client utilizza solo l'SDK ufficiale.")

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    default_headers: Dict[str, str] = {"OpenAI-Beta": "assistants=v2"}
    client_kwargs: Dict[str, object] = {
        "api_key": api_key,
        "default_headers": default_headers,
    }

    base_url_env = (os.getenv("OPENAI_BASE_URL") or "").strip()
    project_env = (os.getenv("OPENAI_PROJECT") or "").strip()
    timeout_env = (os.getenv("OPENAI_TIMEOUT") or "").strip()
    max_retries_env = (os.getenv("OPENAI_MAX_RETRIES") or "").strip()

    if base_url_env:
        client_kwargs["base_url"] = _normalize_base_url(base_url_env)
    if project_env:
        client_kwargs["project"] = project_env
    if timeout_env:
        try:
            client_kwargs["timeout"] = float(timeout_env)
        except ValueError as exc:
            raise ConfigError("OPENAI_TIMEOUT deve essere un numero (secondi).") from exc
    if max_retries_env:
        try:
            client_kwargs["max_retries"] = int(max_retries_env)
        except ValueError as exc:
            raise ConfigError("OPENAI_MAX_RETRIES deve essere un intero.") from exc

    try:
        return OpenAI(**client_kwargs)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ConfigError(
            "La versione del pacchetto 'openai' è troppo vecchia per questi parametri. Aggiorna a openai>=2.0."
        ) from exc
