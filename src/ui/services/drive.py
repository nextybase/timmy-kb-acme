# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable, Dict

from pipeline.exceptions import ConfigError

from ..app_services.drive_cache import _clear_drive_tree_cache, get_drive_tree_cache
from ..components.diff_view import render_drive_local_diff as _render_diff_component

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def invalidate_drive_index(slug: str | None = None) -> None:
    """Svuota la cache dell'indice Drive (delegato alla cache centralizzata)."""
    try:
        _clear_drive_tree_cache()
    except Exception as exc:
        raise ConfigError(f"Drive index cache invalidation failed: {exc!r}") from exc


def render_drive_tree(slug: str) -> Dict[str, Dict[str, Any]]:
    """Renderizza l'albero Drive usando la cache centralizzata (st.cache_data)."""
    getter: Callable[[str], Dict[str, Dict[str, Any]]] = get_drive_tree_cache()
    return getter(slug)


def render_drive_diff(slug: str) -> None:
    """Mostra la diff Drive/locale riutilizzando la cache centralizzata."""
    try:
        getter: Callable[[str], Dict[str, Dict[str, Any]]] = get_drive_tree_cache()
        index = getter(slug)
    except Exception as exc:
        raise ConfigError(f"Drive index load failed (diff unavailable): {exc!r}") from exc

    if st is not None:
        refresh_key = f"drive_tree_refresh_raw_{slug}"
        check_key = f"drive_tree_refresh_check_{slug}"

        if st.button(
            "Aggiorna contenuto raw e verifica PDF",
            key=refresh_key,
            help="Ricarica l'albero Drive e verifica se nelle sottocartelle raw sono presenti file PDF.",
        ):
            st.session_state[check_key] = True
            _clear_drive_tree_cache()
            rerun_fn = getattr(st, "rerun", None)
            if callable(rerun_fn):
                rerun_fn()

        if bool(st.session_state.pop(check_key, False)):
            pdf_count = sum(
                1
                for rel_path, meta in index.items()
                if rel_path.startswith("raw/") and meta.get("type") == "file" and rel_path.lower().endswith(".pdf")
            )
            if pdf_count > 0:
                st.toast(f"Verifica completata: trovati {pdf_count} PDF in raw/.")
            else:
                st.toast("Verifica completata: nessun PDF trovato in raw/.")
            st.caption(f"PDF rilevati ora in raw/: {pdf_count}")

    _render_diff_component(slug, index)
