# SPDX-License-Identifier: GPL-3.0-only
"""Helper centralizzato per gestire tab/slug nei query params Streamlit."""

from __future__ import annotations

from typing import Any, Optional

from ui.utils.stubs import get_streamlit

st = get_streamlit()

_DEF_TAB = "home"


def _normalize(value: Any) -> Optional[str]:
    if isinstance(value, str):
        val = value.strip().lower()
        return val or None
    if isinstance(value, (list, tuple)) and value:
        return _normalize(value[0])
    return None


def get_tab(default: str = _DEF_TAB) -> str:
    """
    Ritorna il valore del tab corrente leggendo dai query params.
    Se il parametro non esiste, restituisce `default` senza forzare l'URL.
    """
    try:
        qp = getattr(st, "query_params", None)
        if qp is None:
            return default
        val = _normalize(qp.get("tab"))
        return val or default
    except Exception:
        return default


def set_tab(tab: str) -> None:
    """Imposta il tab nei query params."""
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None:
            qp["tab"] = _normalize(tab) or _DEF_TAB
    except Exception:
        pass


def clear_tab() -> None:
    """Rimuove il parametro `tab` dai query params (se presente)."""
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None and "tab" in qp:
            del qp["tab"]
    except Exception:
        pass


def get_slug_from_qp() -> Optional[str]:
    """
    Legge lo slug dai query params.
    Ritorna None se non presente o vuoto.
    """
    try:
        qp = getattr(st, "query_params", None)
        if qp is None:
            return None
        return _normalize(qp.get("slug"))
    except Exception:
        return None
