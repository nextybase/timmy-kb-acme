# ui/pages/semantics.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug

st.set_page_config(page_title="Timmy-KB - Semantica", layout="wide")

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

st.subheader("Onboarding semantico")
st.write("Conversione PDF in Markdown, arricchimento frontmatter e generazione README/SUMMARY.")

col_a, col_b = st.columns(2)
with col_a:
    st.button("Converti PDF in Markdown", key="btn_convert", width="stretch")
    st.button("Arricchisci frontmatter", key="btn_enrich", width="stretch")
with col_b:
    st.button("Genera README/SUMMARY", key="btn_generate", width="stretch")
    st.button("Anteprima Docker (HonKit)", key="btn_preview", width="stretch")
