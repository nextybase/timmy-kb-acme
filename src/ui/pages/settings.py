# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/settings.py
from __future__ import annotations

from typing import Callable, Optional

import streamlit as st

from ui.chrome import render_chrome_then_require
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, get_retriever_settings, set_retriever_settings

# ---- Tipi per gli editor YAML ----
YamlEditor = Callable[[str], None]

# Editor YAML (mapping e cartelle) con fallback sicuro
try:
    from ui.components.yaml_editors import edit_cartelle_raw as _edit_cartelle_raw
    from ui.components.yaml_editors import edit_semantic_mapping as _edit_semantic_mapping

    edit_semantic_mapping: Optional[YamlEditor] = _edit_semantic_mapping
    edit_cartelle_raw: Optional[YamlEditor] = _edit_cartelle_raw
except Exception:
    edit_semantic_mapping = None
    edit_cartelle_raw = None

slug = render_chrome_then_require()

st.subheader("Impostazioni")

# ---------------- Retriever ----------------
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

if (int(new_limit), int(new_budget_ms), bool(new_auto)) != (
    int(curr_limit),
    int(curr_budget_ms),
    bool(curr_auto),
):
    set_retriever_settings(int(new_limit), int(new_budget_ms), bool(new_auto))
    try:
        st.toast("Impostazioni retriever salvate")
    except Exception:
        pass

# ---------------- Semantica (YAML) ----------------
st.markdown("---")
st.markdown("### Semantica (YAML)")

col_map, col_cart = st.columns(2)
with col_map:
    if callable(edit_semantic_mapping):
        edit_semantic_mapping(slug)  # semantic/semantic_mapping.yaml
    else:
        st.info("Editor mapping non disponibile.")
with col_cart:
    if callable(edit_cartelle_raw):
        edit_cartelle_raw(slug)  # semantic/cartelle_raw.yaml
    else:
        st.info("Editor cartelle non disponibile.")
