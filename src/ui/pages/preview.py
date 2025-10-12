# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

import streamlit as st

from adapters.preview import start_preview, stop_preview
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from ui.chrome import header, sidebar
from ui.utils import require_active_slug

st.subheader("Preview Docker (HonKit)")

slug = require_active_slug()

header(slug)
sidebar(slug)

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
                name = start_preview(ctx, logger)
                st.session_state["preview_container"] = name
                st.success(f"Preview avviata ({name}).")
            except Exception as exc:
                st.error(f"Impossibile avviare la preview: {exc}")
    with col_stop:
        if st.button("Arresta preview", key="btn_preview_stop", width="stretch"):
            try:
                stop_preview(logger, container_name=st.session_state.get("preview_container"))
                st.session_state.pop("preview_container", None)
                st.info("Preview arrestata.")
            except Exception as exc:
                st.error(f"Arresto fallito: {exc}")
