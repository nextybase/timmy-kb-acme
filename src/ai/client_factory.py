# src/ai/client_factory.py
import os

from openai import OpenAI

from pipeline.exceptions import ConfigError


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
    return OpenAI(api_key=api_key)
