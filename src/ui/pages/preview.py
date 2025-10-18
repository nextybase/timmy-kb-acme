# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

import streamlit as st

from adapters.preview import start_preview, stop_preview
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from ui.chrome import render_chrome_then_require
from ui.utils.status import status_guard

st.subheader("Preview Docker (HonKit)")

slug = render_chrome_then_require()

try:
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    logger = get_structured_logger("ui.preview", run_id=None)
except Exception as e:
    st.error(f"Configurazione non valida: {e}")
else:
    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("Avvia preview", key="btn_preview_start", width="stretch"):
            try:
                with status_guard(
                    "Avvio la preview...",
                    expanded=True,
                    error_label="Errore durante l'avvio della preview",
                ) as status:
                    name = start_preview(ctx, logger)
                    st.session_state["preview_container"] = name
                    if status is not None and hasattr(status, "update"):
                        status.update(label=f"Preview avviata ({name}).", state="complete")
            except Exception as exc:
                st.error(f"Impossibile avviare la preview: {exc}")
    with col_stop:
        if st.button("Arresta preview", key="btn_preview_stop", width="stretch"):
            try:
                with status_guard(
                    "Arresto la preview...",
                    expanded=True,
                    error_label="Errore durante l'arresto della preview",
                ) as status:
                    stop_preview(logger, container_name=st.session_state.get("preview_container"))
                    st.session_state.pop("preview_container", None)
                    if status is not None and hasattr(status, "update"):
                        status.update(label="Preview arrestata.", state="complete")
            except Exception as exc:
                st.error(f"Arresto fallito: {exc}")
