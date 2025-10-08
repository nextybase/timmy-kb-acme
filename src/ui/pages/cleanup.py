# ui/pages/cleanup.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

st.subheader("Cleanup")
st.write("Strumenti di pulizia del workspace e reset stato.")
