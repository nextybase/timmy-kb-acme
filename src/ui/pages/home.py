# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/home.py
from __future__ import annotations

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import header, sidebar
from ui.pages.registry import PagePaths

# ---------------- UI ----------------

header(None)
sidebar(None)

st.subheader("Benvenuto!")
st.write("Per iniziare, crea o apri un workspace cliente.")

# Navigazione affidabile alla pagina "Nuovo cliente" (SSoT)
if hasattr(st, "page_link"):
    st.page_link(PagePaths.NEW_CLIENT, label="Nuovo cliente", icon="➕")
else:
    # Fallback per versioni più vecchie: link diretto al path registrato
    st.link_button("Nuovo cliente", url="/new?tab=new", width="stretch")
