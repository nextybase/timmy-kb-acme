# SPDX-License-Identifier: GPL-3.0-only
"""Gestione della cache dell'albero Drive per la UI Streamlit."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, Optional, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

RenderTreeCallable = Callable[[str], Dict[str, Dict[str, Any]]]

try:
    from ..components.drive_tree import render_drive_tree as _render_drive_tree
except Exception:  # pragma: no cover
    render_drive_tree: Optional[RenderTreeCallable] = None
else:
    render_drive_tree = cast(RenderTreeCallable, _render_drive_tree)


def _drive_tree_uncached(slug: str) -> Dict[str, Dict[str, Any]]:
    if render_drive_tree is None:
        return {}
    return render_drive_tree(slug)


# st.cache_data returns a wrapper preserving the callable signature but mypy sees `Any`.
if st is not None and hasattr(st, "cache_data"):
    _drive_tree_cached: RenderTreeCallable = cast(
        RenderTreeCallable,
        st.cache_data(ttl=timedelta(seconds=90))(_drive_tree_uncached),
    )
else:
    _drive_tree_cached = _drive_tree_uncached


def _clear_drive_tree_cache(*args: Any, **kwargs: Any) -> None:
    """Svuota la cache dell'albero di Drive."""
    clear_fn = getattr(_drive_tree_cached, "clear", None)
    if callable(clear_fn):
        try:
            clear_fn()
        except Exception:  # pragma: no cover
            pass


def get_drive_tree_cache() -> Callable[[str], Dict[str, Dict[str, Any]]]:
    """Restituisce il getter (cachato) dell'albero Drive."""
    return _drive_tree_cached
