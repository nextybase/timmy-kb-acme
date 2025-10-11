# ui/pages/home.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

st.subheader("Benvenuto!")
st.write("Scegli una sezione dal menu in alto per iniziare o crea un nuovo cliente.")

if st.button("Nuovo cliente", key="btn_go_new", width="stretch"):
    try:
        st.query_params["tab"] = "new"
    except Exception:
        pass
    st.rerun()
