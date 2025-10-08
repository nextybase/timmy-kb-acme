# ui/pages/manage.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

st.set_page_config(page_title="Timmy-KB - Gestisci cliente", layout="wide")

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

if st.button("Apri workspace", width="stretch"):
    set_slug(entered_slug)
    st.rerun()
