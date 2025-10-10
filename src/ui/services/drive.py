# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, cast

from ui.components.diff_view import render_drive_local_diff as _render_diff_component
from ui.components.drive_tree import render_drive_tree as _render_tree_component

_DRIVE_INDEX_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def render_drive_tree(slug: str) -> Dict[str, Dict[str, Any]]:
    """
    Bridge per la pagina Manage: renderizza l'albero Drive e memorizza i metadati
    per il successivo confronto locale.
    """
    index = cast(Dict[str, Dict[str, Any]], _render_tree_component(slug))
    _DRIVE_INDEX_CACHE[slug] = index
    return index


def render_drive_diff(slug: str) -> None:
    """
    Mostra la vista diff Drive vs locale riutilizzando l'indice calcolato.
    Se la vista Drive non è stata renderizzata in precedenza, la funzione
    degrada con un indice vuoto.
    """
    index = _DRIVE_INDEX_CACHE.get(slug)
    _render_diff_component(slug, index)
