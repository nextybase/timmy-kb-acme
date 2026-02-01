# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper centralizzato per gestire tab/slug nei query params Streamlit."""

from __future__ import annotations

import logging
from typing import Any, Optional

from pipeline.logging_utils import get_structured_logger
from ui.utils.stubs import get_streamlit

st = get_streamlit()

_DEF_TAB = "home"
_LOGGER = get_structured_logger("ui.route_state")


def _log_route_state_failure(event: str, exc: Exception, *, extra: dict[str, object] | None = None) -> None:
    payload = {"error": repr(exc)}
    if extra:
        payload.update(extra)
    try:
        _LOGGER.warning(event, extra=payload)
    except Exception:
        logging.getLogger("ui.route_state").warning("%s error=%r", event, exc)


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
    except Exception as exc:
        _log_route_state_failure(
            "ui.route_state.get_tab_failed",
            exc,
            extra={"op": "get", "param": "tab"},
        )
        return default


def set_tab(tab: str) -> None:
    """Imposta il tab nei query params."""
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None:
            qp["tab"] = _normalize(tab) or _DEF_TAB
    except Exception as exc:
        _log_route_state_failure(
            "ui.route_state.set_tab_failed",
            exc,
            extra={"op": "set", "param": "tab", "value": tab},
        )


def clear_tab() -> None:
    """Rimuove il parametro `tab` dai query params (se presente)."""
    try:
        qp = getattr(st, "query_params", None)
        if qp is not None and "tab" in qp:
            del qp["tab"]
    except Exception as exc:
        _log_route_state_failure(
            "ui.route_state.clear_tab_failed",
            exc,
            extra={"op": "clear", "param": "tab"},
        )


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
    except Exception as exc:
        _log_route_state_failure(
            "ui.route_state.get_slug_failed",
            exc,
            extra={"op": "parse", "param": "slug"},
        )
        return None
