# SPDX-License-Identifier: GPL-3.0-or-later
# ui/pages/manage.py
from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """
    Importa una funzione se disponibile, altrimenti None.
    fn_path formato: "package.module:function".
    """
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Prova ad importare i renderer: se non ci sono mostriamo un messaggio informativo.
_render_drive_tree = _safe_get("ui.services.drive:render_drive_tree")
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")
_render_tags_editor = _safe_get("ui.services.tags:render_tags_editor")

# TODO: collega qui la tua funzione Vision reale e assegna `run_vision`.
# Esempio: from semantic.api import build_semantic_from_vision as run_vision
# Se lasci None, la UI mostrera un placeholder informativo.
run_vision: Callable[[str], None] | None = None  # placeholder

# Consumo flag Vision (impostato da new_client)
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

st.subheader("Gestione cliente")

entered_slug = st.text_input(
    "Slug cliente",
    value=slug or "",
    placeholder="es. acme",
    key="manage_slug",
)

if st.button("Apri workspace", key="manage_open_workspace", width="stretch"):
    set_slug((entered_slug or "").strip())
    st.rerun()

if not slug:
    st.info("Inserisci uno slug e premi **Apri workspace**.")
    st.stop()

# Blocchi principali (Drive / Diff / Tag) come da guida UI.
drive_col, diff_col, tags_col = st.columns((1.2, 1, 1))

with drive_col:
    st.markdown("##### Drive")
    if _render_drive_tree is not None:
        try:
            _render_drive_tree(slug)
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Drive: {e}")
    else:
        st.info("Vista Drive non disponibile.")

with diff_col:
    st.markdown("##### Diff")
    if _render_drive_diff is not None:
        try:
            _render_drive_diff(slug)
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Diff: {e}")
    else:
        st.info("Vista Diff non disponibile.")

with tags_col:
    st.markdown("##### Tag")
    if _render_tags_editor is not None:
        try:
            _render_tags_editor(slug)
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nell'editor Tag: {e}")
    else:
        st.info("Editor Tag non disponibile.")
