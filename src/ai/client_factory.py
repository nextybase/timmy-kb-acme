# src/ai/client_factory.py
from __future__ import annotations

import inspect
import os
from typing import TYPE_CHECKING, Any, Dict

from pipeline.exceptions import ConfigError

if TYPE_CHECKING:
    from openai import OpenAI  # pragma: no cover

# Default pubblico; può essere sovrascritto via ENV (OPENAI_BASE_URL)
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

# Flag opzionale per forzare SEMPRE l'uso di httpx anche se il costruttore semplice dell’SDK non esplode.
# Utile in ambienti UI (es. Streamlit) dove il trasporto interno può essere fragile.
_FORCE_HTTPX = (os.getenv("OPENAI_FORCE_HTTPX") or "0").strip().lower() in {"1", "true", "yes", "on"}


def _build_http_client(base_url: str):
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
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        follow_redirects=True,
        http2=True,
    )


def _supports_kwarg(ctor: Any, name: str) -> bool:
    """Controlla in modo difensivo se il costruttore/funzione supporta un certo parametro."""
    try:
        sig = inspect.signature(ctor)  # type: ignore[arg-type]
        return name in sig.parameters
    except Exception:
        return False


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
    project_env = (os.getenv("OPENAI_PROJECT") or "").strip()
    base_url = base_url_env or _DEFAULT_OPENAI_BASE_URL
    timeout_sec = float(os.getenv("OPENAI_TIMEOUT", "120"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

    # --- Branch: forza httpx se richiesto (es. UI/Streamlit) ---
    if _FORCE_HTTPX:
        # Proviamo a chiamare _build_http_client in modo flessibile (alcuni test lo monkeypatchano senza argomenti).
        try:
            if _supports_kwarg(_build_http_client, "base_url"):
                http_client = _build_http_client(base_url)  # type: ignore[misc]
            else:
                http_client = _build_http_client()  # type: ignore[call-arg]
        except TypeError:
            http_client = _build_http_client()  # type: ignore[call-arg]

        forced_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "http_client": http_client,
            "default_headers": default_headers,
        }
        if project_env and _supports_kwarg(OpenAI, "project"):
            forced_kwargs["project"] = project_env
        if base_url_env and _supports_kwarg(OpenAI, "base_url"):
            forced_kwargs["base_url"] = base_url_env
        if _supports_kwarg(OpenAI, "timeout"):
            forced_kwargs["timeout"] = timeout_sec
        if _supports_kwarg(OpenAI, "max_retries"):
            forced_kwargs["max_retries"] = max_retries
        try:
            return OpenAI(**forced_kwargs)  # type: ignore[arg-type]
        except TypeError:
            # Estremo fallback: riduci ai minimi termini per massima compatibilità
            forced_kwargs.pop("project", None)
            forced_kwargs.pop("base_url", None)
            forced_kwargs.pop("max_retries", None)
            forced_kwargs.pop("timeout", None)
            return OpenAI(**forced_kwargs)  # type: ignore[arg-type]

    # --- Primo tentativo minimalista (alcuni test si aspettano http_client=None al primo giro)
    # Passiamo SOLO i parametri sicuramente supportati e minimi.
    simple_kwargs: Dict[str, Any] = {"api_key": api_key, "default_headers": default_headers}
    try:
        return OpenAI(**simple_kwargs)  # type: ignore[arg-type]
    except TypeError:
        # --- Fallback robusto (httpx dedicato) ---
        # Nei test _build_http_client può essere monkeypatchato come lambda senza argomenti:
        # decidiamo a runtime se passare base_url o meno.
        try:
            if _supports_kwarg(_build_http_client, "base_url"):
                http_client = _build_http_client(base_url)  # type: ignore[misc]
            else:
                http_client = _build_http_client()  # type: ignore[call-arg]
        except TypeError:
            http_client = _build_http_client()  # type: ignore[call-arg]

        fallback_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "http_client": http_client,
            "default_headers": default_headers,
        }
        # Aggiungi project/base_url/timeout/retries SE la build del client lo supporta
        if project_env and _supports_kwarg(OpenAI, "project"):
            fallback_kwargs["project"] = project_env
        if base_url_env and _supports_kwarg(OpenAI, "base_url"):
            fallback_kwargs["base_url"] = base_url_env
        if _supports_kwarg(OpenAI, "timeout"):
            fallback_kwargs["timeout"] = timeout_sec
        if _supports_kwarg(OpenAI, "max_retries"):
            fallback_kwargs["max_retries"] = max_retries

        try:
            return OpenAI(**fallback_kwargs)  # type: ignore[arg-type]
        except TypeError:
            # Estremo fallback: riduci ai minimi termini per massima compatibilità
            fallback_kwargs.pop("project", None)
            fallback_kwargs.pop("base_url", None)
            fallback_kwargs.pop("max_retries", None)
            fallback_kwargs.pop("timeout", None)
            return OpenAI(**fallback_kwargs)  # type: ignore[arg-type]
