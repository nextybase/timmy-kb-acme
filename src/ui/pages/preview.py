# ui/pages/preview.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

st.set_page_config(page_title="Timmy-KB - Preview Docker", layout="wide")

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

st.subheader("Preview Docker (HonKit)")
st.write("Se Docker non è attivo, la preview viene saltata automaticamente.")
