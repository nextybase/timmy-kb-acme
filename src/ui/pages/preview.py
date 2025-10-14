# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import streamlit as st

from adapters.preview import start_preview, stop_preview
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from ui.chrome import render_chrome_then_require


@contextmanager
def status_guard(label: str, *, error_label: str | None = None, **kwargs: Any) -> Iterator[Any]:
    clean_label = label.rstrip(" .…")
    error_prefix = error_label or (f"Errore durante {clean_label}" if clean_label else "Errore")
    with st.status(label, **kwargs) as status:
        try:
            yield status
        except Exception as exc:
            if status is not None and hasattr(status, "update"):
                status.update(label=f"{error_prefix}: {exc}", state="error")
            raise


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
