# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/settings.py
from __future__ import annotations

import streamlit as st

from ui.chrome import header, sidebar
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, get_retriever_settings, set_retriever_settings
from ui.utils import get_slug, set_slug

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

st.subheader("Impostazioni")

st.markdown("### Retriever")
curr_limit, curr_budget_ms, curr_auto = get_retriever_settings()

new_limit = st.number_input(
    "Candidate limit",
    min_value=MIN_CANDIDATE_LIMIT,
    max_value=MAX_CANDIDATE_LIMIT,
    value=curr_limit,
    step=500,
    key="retr_limit_page",
    help="Numero massimo di candidati restituiti dal retriever.",
)
new_budget_ms = st.number_input(
    "Budget latenza (ms)",
    min_value=0,
    max_value=2000,
    value=curr_budget_ms,
    step=50,
    key="retr_budget_page",
    help="Tempo massimo di ricerca (ms).",
)
new_auto = st.toggle("Auto per budget", value=curr_auto, key="retr_auto_page")

if (int(new_limit), int(new_budget_ms), bool(new_auto)) != (int(curr_limit), int(curr_budget_ms), bool(curr_auto)):
    set_retriever_settings(int(new_limit), int(new_budget_ms), bool(new_auto))
    try:
        st.toast("Impostazioni retriever salvate")
    except Exception:
        pass
