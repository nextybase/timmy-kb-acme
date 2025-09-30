from __future__ import annotations

from typing import Any

import streamlit as st

from ui.clients_store import set_state
from ui.services.drive_runner import build_drive_from_mapping, download_raw_from_drive, emit_readmes_for_raw


def render_drive_tab(*, log: Any, slug: str) -> None:
    st.subheader("Google Drive: struttura e contenuti RAW")

    colA, colB = st.columns(2)
    with colA:
        if st.button("1) Crea/aggiorna struttura Drive", key="btn_drive_create", use_container_width=True):
            try:
                prog = st.progress(0)
                status = st.empty()

                def _cb(step: int, total: int, label: str) -> None:
                    pct = int(step * 100 / max(total, 1))
                    prog.progress(pct)
                    status.markdown(f"{pct}% - {label}")

                ids = build_drive_from_mapping(
                    slug=slug, client_name=st.session_state.get("client_name", ""), progress=_cb
                )
                st.success(f"Struttura creata: {ids}")
                set_state(slug, "inizializzato")
                log.info({"event": "drive_structure_created", "slug": slug, "ids": ids})
            except Exception as e:
                st.exception(e)
    with colB:
        if st.button("2) Genera README in raw/", key="btn_drive_readmes", type="primary", use_container_width=True):
            try:
                result = emit_readmes_for_raw(slug=slug, ensure_structure=True)
                st.success(f"README creati: {len(result)}")
                log.info({"event": "raw_readmes_uploaded", "slug": slug, "count": len(result)})
                st.session_state["drive_readmes_done"] = True
            except Exception as e:
                st.exception(e)

    if st.session_state.get("drive_readmes_done"):
        st.markdown("---")
        st.subheader("Download contenuti su raw/")
        if st.button("Scarica PDF da Drive in raw/", key="btn_drive_download_raw", use_container_width=True):
            try:
                res = download_raw_from_drive(slug=slug)
                count = len(res) if hasattr(res, "__len__") else None
                msg_tail = f" ({count} file)" if count is not None else ""
                st.success(f"Download completato{msg_tail}.")
                set_state(slug, "pronto")
                log.info({"event": "drive_raw_downloaded", "slug": slug, "count": count})
                st.session_state["raw_downloaded"] = True
                st.session_state["raw_ready"] = True
            except Exception as e:
                st.exception(e)
