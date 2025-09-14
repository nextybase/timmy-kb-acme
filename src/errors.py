# src/pipeline/errors.py
"""Gerarchia di errori comune per Timmy KB.

Nota: manteniamo le eccezioni come sotto-classi di ValueError/RuntimeError
per compatibilità con eventuali catch generici già presenti.
"""


class TimmyError(Exception):
    """Base per errori applicativi Timmy."""


class ConfigError(ValueError, TimmyError):
    """Errore di configurazione (es. config.yaml mancante o invalido)."""


class RetrieverError(ValueError, TimmyError):
    """Errore di validazione o uso del retriever (parametri, limiti, ecc.)."""


class PreviewError(RuntimeError, TimmyError):
    """Errore nella fase di preview (es. Docker/HonKit)."""


class PushError(RuntimeError, TimmyError):
    """Errore nella fase di push (es. credenziali GitHub, permessi)."""


__all__ = [
    "TimmyError",
    "ConfigError",
    "RetrieverError",
    "PreviewError",
    "PushError",
]
