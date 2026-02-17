# SPDX-License-Identifier: GPL-3.0-or-later
"""Gestione della cache dell'albero Drive per la UI Streamlit."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, cast

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


# NOTE:
# render_drive_tree() contiene widget Streamlit (es. pulsanti azione file).
# Caching di funzioni con widget genera CachedWidgetWarning.
# Manteniamo quindi questo path esplicitamente non-cachato.
_drive_tree_cached: RenderTreeCallable = _drive_tree_uncached


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
