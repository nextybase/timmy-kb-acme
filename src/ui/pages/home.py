# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/home.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar

# ---------------- UI ----------------

header(None)
sidebar(None)

st.subheader("Benvenuto!")
st.write("Per iniziare, crea o apri un workspace cliente.")

# Navigazione affidabile alla pagina "Nuovo cliente"
# Nota: il valore deve essere il *percorso del file* usato in onboarding_ui.py
# quando hai fatto st.Page("src/ui/pages/new_client.py", title="Nuovo cliente", url_path="new")
if hasattr(st, "page_link"):
    st.page_link(
        "src/ui/pages/new_client.py",  # <— percorso file relativo all’entrypoint
        label="Nuovo cliente",
        icon="➕",
    )
else:
    # Fallback per versioni più vecchie: link diretto al path registrato
    st.link_button("Nuovo cliente", url="/new?tab=new", width="stretch")
