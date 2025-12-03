# SPDX-License-Identifier: GPL-3.0-or-later
# src/ai/client_factory.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings


def _normalize_base_url(raw: str) -> str:
    base = raw.strip()
    if not base:
        return "https://api.openai.com/v1"
    if "://" not in base:
        base = "https://" + base
    if not base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base


def make_openai_client():
    """
    Costruisce un client OpenAI (SDK >= 2) applicando le policy del progetto.

    Richiede che `OPENAI_API_KEY` sia impostata.
    """
    ensure_dotenv_loaded()

    try:
        api_key = get_env_var("OPENAI_API_KEY", required=True)
    except KeyError as exc:
        raise ConfigError("Manca la API key. Imposta la variabile di ambiente OPENAI_API_KEY.") from exc

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    default_headers: Dict[str, str] = {"OpenAI-Beta": "assistants=v2"}
    client_kwargs: Dict[str, object] = {
        "api_key": api_key,
        "default_headers": default_headers,
    }

    base_url_env = get_env_var("OPENAI_BASE_URL", default=None)
    project_env = get_env_var("OPENAI_PROJECT", default=None)
    settings_obj = _load_settings()
    if settings_obj is not None:
        openai_cfg = settings_obj.openai_settings
        client_kwargs["timeout"] = float(openai_cfg.timeout)
        client_kwargs["max_retries"] = int(openai_cfg.max_retries)
        if openai_cfg.http2_enabled:
            client_kwargs["http2"] = True
        LOGGER.info("openai.client.config_from_yaml", extra={"source": "config"})

    if base_url_env:
        client_kwargs["base_url"] = _normalize_base_url(base_url_env)
    if project_env:
        client_kwargs["project"] = project_env

    try:
        return OpenAI(**client_kwargs)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ConfigError(
            "La versione del pacchetto 'openai' è troppo vecchia per questi parametri. Aggiorna a openai>=2.0."
        ) from exc


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_settings() -> Optional[Settings]:
    try:
        return Settings.load(_REPO_ROOT)
    except Exception:
        return None


LOGGER = get_structured_logger("ai.client_factory")
