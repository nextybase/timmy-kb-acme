# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione se disponibile, altrimenti None. Formato: 'pkg.mod:func'."""
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Usa i "services" (gestiscono cache e bridging verso i component)
_render_drive_tree = _safe_get("ui.services.drive:render_drive_tree")
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")

# Se vuoi collegare Vision, assegna qui la funzione: run_vision(slug) -> None
run_vision: Optional[Callable[[str], None]] = None

# Se new_client ha richiesto Vision, eseguila qui
if st.session_state.pop("vision_init_requested", False):
    pending_slug = get_slug()
    if not pending_slug:
        st.warning("Nessuno slug attivo: impossibile avviare la procedura Vision.")
    elif run_vision is None:
        st.info("Procedura Vision non collegata: assegna `run_vision(slug)` per generare gli YAML in semantic/.")
    else:
        with st.status("Esecuzione Vision...", expanded=True):
            run_vision(pending_slug)
        st.success("Vision completata: YAML generati in `semantic/`.")

# ---------------- UI ----------------

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

# Mostra input/pulsante SOLO se lo slug NON è settato
if not slug:
    entered_slug = st.text_input(
        "Slug cliente",
        value="",
        placeholder="es. acme",
        key="manage_slug",
    )

    if st.button("Apri workspace", key="manage_open_workspace", width="stretch"):
        set_slug((entered_slug or "").strip())
        st.rerun()

    st.info("Inserisci uno slug e premi **Apri workspace**.")
    st.stop()

# Da qui in poi: slug presente → mostra direttamente le viste operative
col_left, col_right = st.columns(2)

with col_left:
    if _render_drive_tree is not None:
        try:
            _render_drive_tree(slug)  # restituisce anche indice cachato
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Drive: {e}")
    else:
        st.info("Vista Drive non disponibile.")

with col_right:
    if _render_drive_diff is not None:
        try:
            _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Diff: {e}")
    else:
        st.info("Vista Diff non disponibile.")
