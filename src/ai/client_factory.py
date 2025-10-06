# src/ai/client_factory.py
import os
from typing import TYPE_CHECKING

from pipeline.exceptions import ConfigError

if TYPE_CHECKING:
    from openai import OpenAI

_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _build_http_client():
    """Crea un httpx.Client compatibile con le versioni >=0.28."""
    try:
        import httpx
    except ImportError as exc:
        raise ConfigError("Per usare il fallback OpenAI serve installare httpx.") from exc

    return httpx.Client(
        base_url=_OPENAI_BASE_URL,
        timeout=httpx.Timeout(timeout=600.0, connect=5.0),
        limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        follow_redirects=True,
    )


def make_openai_client() -> "OpenAI":
    """
    Crea e restituisce un client OpenAI.
    Ordine di ricerca chiave:
    1) OPENAI_API_KEY_FOLDER (dedicata agli assistenti su file/folder)
    2) OPENAI_API_KEY (compatibilita' storica)
    """
    api_key = os.getenv("OPENAI_API_KEY_FOLDER") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError(
            "Manca la API key. Imposta almeno OPENAI_API_KEY_FOLDER (preferito) " "oppure OPENAI_API_KEY come fallback."
        )

    try:
        from openai import OpenAI  # type: ignore import
    except ImportError as exc:
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    default_headers = {"OpenAI-Beta": "assistants=v2"}

    # Qui NON logghiamo la chiave. Eventuali timeout/proxy si aggiungono qui.
    try:
        return OpenAI(api_key=api_key, default_headers=default_headers)
    except TypeError as exc:
        if "proxies" not in str(exc):
            raise
        # Fallback per httpx>=0.28 (rimozione kwarg proxies).
        return OpenAI(
            api_key=api_key,
            http_client=_build_http_client(),
            default_headers=default_headers,
        )
