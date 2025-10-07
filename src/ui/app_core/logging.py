"""Logica di configurazione logging per l'app Streamlit."""

from __future__ import annotations

import logging


def _setup_logging() -> logging.Logger:
    """Configura e restituisce il logger principale della UI."""
    logger = logging.getLogger("ui.new_client")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
