# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/ui_controls.py
from __future__ import annotations

from typing import Any, cast

from ui.types import StreamlitLike
from ui.utils.stubs import get_streamlit


def _st() -> StreamlitLike:
    """Recupera dinamicamente il modulo streamlit (o lo stub) per supportare i test che lo monkeypatchano."""
    return cast(StreamlitLike, get_streamlit())


def columns3() -> tuple[Any, Any, Any]:
    """
    Restituisce sempre 3 'colonne' utilizzabili anche in test/headless.
    - Tenta prima columns([1,1,1]), poi columns(3)
    - Se non disponibile o errore → fallback a (st, st, st)
    - Se <3 colonne → padding con l'ultima
    """
    st = _st()
    make = getattr(st, "columns", None)
    if not callable(make):
        return (st, st, st)
    try:
        cols = list(make([1, 1, 1]))
    except Exception:
        try:
            cols = list(make(3))
        except Exception:
            return (st, st, st)
    if not cols:
        return (st, st, st)
    while len(cols) < 3:
        cols.append(cols[-1])
    return cast(Any, cols[0]), cast(Any, cols[1]), cast(Any, cols[2])


def button(container: Any, *args: Any, **kwargs: Any) -> bool:
    """
    Invoca container.button(...) se presente; altrimenti degrada a st.button(...).
    Gestisce eccezioni generiche degradando al fallback.
    """
    fn = getattr(container, "button", None)
    if callable(fn):
        try:
            return bool(fn(*args, **kwargs))
        except Exception:
            pass
    st = _st()
    fallback = getattr(st, "button", None)
    return bool(fallback(*args, **kwargs)) if callable(fallback) else False


def column_button(container: Any, label: str, **kwargs: Any) -> bool:
    """
    Pulsante resiliente per layout a colonne.
    - Se lo stub non supporta parametri (es. width), rimuove la chiave incriminata e ritenta.
    - Fallback a st.button(...) se container.button non esiste.
    """
    fn = getattr(container, "button", None)
    if callable(fn):
        try:
            return bool(fn(label, **kwargs))
        except TypeError as exc:
            # Alcuni stub non supportano 'width' o altri kw opzionali
            if "width" in str(exc):
                kwargs.pop("width", None)
                return bool(fn(label, **kwargs))
            raise
    st = _st()
    fallback = getattr(st, "button", None)
    if callable(fallback):
        try:
            return bool(fallback(label, **kwargs))
        except TypeError as exc:
            if "width" in str(exc):
                kwargs.pop("width", None)
                return bool(fallback(label, **kwargs))
            raise
    return False


__all__ = ["columns3", "button", "column_button"]
