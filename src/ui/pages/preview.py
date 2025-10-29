# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

from ui.errors import to_user_message
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button

st = get_streamlit()

from adapters.preview import start_preview, stop_preview
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from ui.chrome import render_chrome_then_require
from ui.utils.status import status_guard

st.subheader("Preview Docker (HonKit)")

slug = render_chrome_then_require()

try:
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    logger = get_structured_logger("ui.preview", context=ctx)
except Exception as exc:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)
else:
    col_start, col_stop = st.columns(2)
    if _column_button(col_start, "Avvia preview", key="btn_preview_start", width="stretch"):
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
            title, body, caption = to_user_message(exc)
            st.error(title)
            if caption or body:
                st.caption(caption or body)
    if _column_button(col_stop, "Arresta preview", key="btn_preview_stop", width="stretch"):
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
            title, body, caption = to_user_message(exc)
            st.error(title)
            if caption or body:
                st.caption(caption or body)
