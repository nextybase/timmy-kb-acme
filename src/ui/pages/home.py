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
st.write("Scegli una sezione dal menu in alto per iniziare.")
st.link_button("Guida UI (Streamlit)", "docs/guida_ui.md", width="stretch")
