# src/ai/client_factory.py
from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from pipeline.exceptions import ConfigError

try:
    # Carica .env dal cwd o, in fallback, dalla root repo
    from dotenv import find_dotenv, load_dotenv  # type: ignore

    _DOTENV_LOADED = bool(load_dotenv(find_dotenv(usecwd=True), override=False))
    if not _DOTENV_LOADED:
        repo_root = Path(__file__).resolve().parents[2]
        env_path = repo_root / ".env"
        if env_path.exists():
            _DOTENV_LOADED = bool(load_dotenv(env_path, override=False))
except Exception:
    # python-dotenv non installato: proseguiamo senza, ma è la causa tipica di env “vuote”
    _DOTENV_LOADED = False


def _bool_env(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _supports_kwarg(fn: Any, kw: str) -> bool:
    try:
        sig = inspect.signature(fn)  # type: ignore[arg-type]
        return kw in sig.parameters
    except Exception:
        return False


if TYPE_CHECKING:
    from openai import OpenAI  # pragma: no cover

# Default pubblico; può essere sovrascritto via ENV (OPENAI_BASE_URL)
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _build_http_client(base_url: str | None = None):
    """
    Crea un httpx.Client moderno (>=0.28) con timeout/livelli sensati.
    NB: httpx è opzionale; lo usiamo per avere pieno controllo del trasporto.
    """
    try:
        import httpx  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("Per usare il client OpenAI con trasporto httpx serve installare 'httpx'.") from exc

    # Timeout bilanciati: connessione rapida, letture/scritture più generose (upload PDF VS).
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=120.0, pool=None)
    http2_on = _bool_env("OPENAI_HTTP2", True)
    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        "limits": httpx.Limits(max_connections=200, max_keepalive_connections=50),
        "follow_redirects": True,
        "http2": http2_on,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return httpx.Client(**kwargs)


def make_openai_client() -> "OpenAI":
    """
    Crea e restituisce un client OpenAI “hardened” (SDK 2.x).

    Ricerca API key:
      1) OPENAI_API_KEY_FOLDER (compat retro del progetto)
      2) OPENAI_API_KEY

    Config opzionali:
      - OPENAI_BASE_URL (relay/proxy o endpoint alternativo)
      - OPENAI_PROJECT (Projects)
      - OPENAI_TIMEOUT (secondi, default 120)
      - OPENAI_MAX_RETRIES (default 2)
      - OPENAI_FORCE_HTTPX (1/true per forzare httpx)
    """
    api_key = os.getenv("OPENAI_API_KEY_FOLDER") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError(
            "Manca la API key. Imposta almeno OPENAI_API_KEY_FOLDER (preferito) oppure OPENAI_API_KEY come fallback."
        )

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    # Header raccomandato per Assistants v2; innocuo per gli altri endpoint.
    default_headers: Dict[str, str] = {"OpenAI-Beta": "assistants=v2"}

    # Config comuni
    base_url_env = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if base_url_env.startswith("#") or base_url_env.lower().startswith(("opzionale", "optional")):
        base_url_env = ""
    project_env = (os.getenv("OPENAI_PROJECT") or "").strip()
    base_url = base_url_env or _DEFAULT_OPENAI_BASE_URL
    # Normalizza errori comuni: dominio senza schema e/o path /v1 mancante
    if "://" not in base_url:
        base_url = "https://" + base_url
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    timeout_sec = float(os.getenv("OPENAI_TIMEOUT", "120"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

    force_httpx = _bool_env("OPENAI_FORCE_HTTPX", False)

    simple_exc: Exception | None = None
    simple_client: OpenAI | None = None  # type: ignore[name-defined]
    try:
        simple_client = OpenAI(api_key=api_key, default_headers=default_headers)  # type: ignore[call-arg]
    except TypeError as exc:
        simple_exc = exc

    if not force_httpx and simple_exc is None and simple_client is not None:
        return simple_client

    # --- Fallback httpx dedicato ---
    try:
        if _supports_kwarg(_build_http_client, "base_url"):
            http_client = _build_http_client(base_url)  # type: ignore[misc]
        else:
            http_client = _build_http_client()  # type: ignore[call-arg]
    except TypeError:
        http_client = _build_http_client()  # type: ignore[call-arg]

    client_kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "http_client": http_client,
        "default_headers": default_headers,
    }
    if project_env and _supports_kwarg(OpenAI, "project"):
        client_kwargs["project"] = project_env
    if base_url_env and _supports_kwarg(OpenAI, "base_url"):
        client_kwargs["base_url"] = base_url_env
    if _supports_kwarg(OpenAI, "timeout"):
        client_kwargs["timeout"] = timeout_sec
    if _supports_kwarg(OpenAI, "max_retries"):
        client_kwargs["max_retries"] = max_retries

    try:
        return OpenAI(**client_kwargs)  # type: ignore[arg-type]
    except TypeError:
        # Estremo fallback: riduci ai minimi termini per massima compatibilità
        client_kwargs.pop("project", None)
        client_kwargs.pop("base_url", None)
        client_kwargs.pop("max_retries", None)
        client_kwargs.pop("timeout", None)
        return OpenAI(**client_kwargs)  # type: ignore[arg-type]
