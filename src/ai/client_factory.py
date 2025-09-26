# src/ai/client_factory.py
import os

import httpx
from openai import OpenAI

from pipeline.exceptions import ConfigError

_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _build_http_client() -> httpx.Client:
    """Crea un httpx.Client compatibile con le versioni >=0.28."""

    return httpx.Client(
        base_url=_OPENAI_BASE_URL,
        timeout=httpx.Timeout(timeout=600.0, connect=5.0),
        limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        follow_redirects=True,
    )


def make_openai_client() -> OpenAI:
    """
    Crea e restituisce un client OpenAI.
    Ordine di ricerca chiave:
    1) OPENAI_API_KEY_FOLDER (dedicata agli assistenti su file/folder)
    2) OPENAI_API_KEY (fallback legacy)
    """
    api_key = os.getenv("OPENAI_API_KEY_FOLDER") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigError(
            "Manca la API key. Imposta almeno OPENAI_API_KEY_FOLDER (preferito) " "oppure OPENAI_API_KEY come fallback."
        )
    # Qui NON logghiamo la chiave. Eventuali timeout/proxy si aggiungono qui.
    try:
        return OpenAI(api_key=api_key)
    except TypeError as exc:
        if "proxies" not in str(exc):
            raise
        # Fallback per httpx>=0.28 (rimozione kwarg `proxies`).
        return OpenAI(api_key=api_key, http_client=_build_http_client())
