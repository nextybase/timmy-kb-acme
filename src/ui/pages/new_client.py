# src/ui/pages/new_client.py
from __future__ import annotations

from typing import Optional

import streamlit as st

from src.pre_onboarding import ensure_local_workspace_for_ui  # già esistente nel progetto

# importa gli helper che già usi nell'app
from src.ui.chrome import header, sidebar
from src.ui.utils.query_params import set_slug  # o equivalente helper set_slug(...)


def _go_manage() -> None:
    st.query_params["tab"] = "manage"
    st.rerun()


header(None)
sidebar(None)

st.subheader("Nuovo cliente")

slug = st.text_input("Slug cliente", placeholder="es. acme-srl", key="new_slug")
name = st.text_input("Nome cliente (opzionale)", placeholder="es. ACME Srl", key="new_name")
pdf = st.file_uploader("Vision Statement (PDF, opzionale)", type=["pdf"], key="new_vs_pdf")

create = st.button("Crea workspace", type="primary", key="btn_create_client", width="stretch")

if create:
    s = (slug or "").strip()
    if not s:
        st.warning("Inserisci uno slug valido.")
        st.stop()

    pdf_bytes: Optional[bytes] = pdf.read() if pdf is not None else None
    try:
        ensure_local_workspace_for_ui(s, client_name=(name or None), vision_statement_pdf=pdf_bytes)
        set_slug(s)
        st.success("Workspace creato con successo.")
        _go_manage()
    except Exception as e:  # pragma: no cover
        st.error(f"Impossibile creare il workspace: {e}")
