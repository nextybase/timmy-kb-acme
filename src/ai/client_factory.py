# SPDX-License-Identifier: GPL-3.0-or-later
# src/ai/client_factory.py
from __future__ import annotations

from typing import Dict, Optional

from pipeline.env_utils import ensure_dotenv_loaded, get_bool, get_env_var
from pipeline.exceptions import ConfigError


def _normalize_base_url(raw: str) -> str:
    base = raw.strip()
    if not base:
        return "https://api.openai.com/v1"
    if "://" not in base:
        base = "https://" + base
    if not base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base


def _optional_env(name: str) -> Optional[str]:
    try:
        return get_env_var(name)
    except Exception:
        return None


def make_openai_client():
    """
    Costruisce un client OpenAI (SDK >= 2) applicando le policy del progetto.

    Richiede che `OPENAI_API_KEY` sia impostata.
    Le variabili legacy (`OPENAI_API_KEY_FOLDER`, `OPENAI_FORCE_HTTPX`) non sono più supportate.
    """
    ensure_dotenv_loaded()

    legacy_key = _optional_env("OPENAI_API_KEY_FOLDER")
    try:
        api_key = get_env_var("OPENAI_API_KEY", required=True)
    except KeyError as exc:
        raise ConfigError("Manca la API key. Imposta la variabile di ambiente OPENAI_API_KEY.") from exc

    if legacy_key and not api_key:
        raise ConfigError(
            "OPENAI_API_KEY_FOLDER non è più supportata. Sposta il valore in OPENAI_API_KEY (.env/ambiente)."
        )

    if get_bool("OPENAI_FORCE_HTTPX", default=False):
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

    base_url_env = _optional_env("OPENAI_BASE_URL")
    project_env = _optional_env("OPENAI_PROJECT")
    timeout_env = _optional_env("OPENAI_TIMEOUT")
    max_retries_env = _optional_env("OPENAI_MAX_RETRIES")

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
