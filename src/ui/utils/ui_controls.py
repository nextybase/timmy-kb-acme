# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/ui_controls.py
from __future__ import annotations

from typing import Any, cast

from ui.types import StreamlitLike
from ui.utils.stubs import get_streamlit


def _st() -> StreamlitLike:
    """Recupera dinamicamente il modulo streamlit (contrattuale nel runtime Beta 1.0)."""
    return cast(StreamlitLike, get_streamlit())


def columns3() -> tuple[Any, Any, Any]:
    """
    Restituisce 3 colonne via Streamlit.
    """
    st = _st()
    cols = list(st.columns([1, 1, 1]))
    return cast(Any, cols[0]), cast(Any, cols[1]), cast(Any, cols[2])


def button(container: Any, *args: Any, **kwargs: Any) -> bool:
    """
    Invoca container.button(...).
    """
    fn = getattr(container, "button")
    return bool(fn(*args, **kwargs))


def column_button(container: Any, label: str, **kwargs: Any) -> bool:
    """
    Pulsante resiliente per layout a colonne.
    """
    fn = getattr(container, "button")
    return bool(fn(label, **kwargs))


__all__ = ["columns3", "button", "column_button"]
