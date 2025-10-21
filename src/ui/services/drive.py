# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable, Dict

from ..app_services.drive_cache import _clear_drive_tree_cache, get_drive_tree_cache
from ..components.diff_view import render_drive_local_diff as _render_diff_component


def invalidate_drive_index(slug: str | None = None) -> None:
    """Svuota la cache dell'indice Drive (delegato alla cache centralizzata)."""
    try:
        _clear_drive_tree_cache()
    except Exception:
        pass


def render_drive_tree(slug: str) -> Dict[str, Dict[str, Any]]:
    """Renderizza l'albero Drive usando la cache centralizzata (st.cache_data)."""
    getter: Callable[[str], Dict[str, Dict[str, Any]]] = get_drive_tree_cache()
    return getter(slug)


def render_drive_diff(slug: str) -> None:
    """Mostra la diff Drive↔locale riutilizzando la cache centralizzata."""
    try:
        getter: Callable[[str], Dict[str, Dict[str, Any]]] = get_drive_tree_cache()
        index = getter(slug)
    except Exception:
        index = {}
    _render_diff_component(slug, index)
