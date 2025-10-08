# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import streamlit as st

# SSoT: limiti e persistenza retriever
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, get_retriever_settings, set_retriever_settings


def header(slug: str | None) -> None:
    """Header minimale con ancorina e titolo."""
    st.html("<a id='top'></a>")  # ancorina sicura
    st.title("Timmy-KB • Onboarding")
    if slug:
        st.caption(f"Cliente: **{slug}**")


def sidebar(slug: str | None) -> None:
    """Sidebar con azioni rapide e settaggi retriever (persistiti su config.yaml)."""
    with st.sidebar:
        st.subheader("Azioni rapide")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.button("Aggiorna Drive", key="btn_refresh", width="stretch")
        with col2:
            st.button("Dummy KB", key="btn_dummy", width="stretch")
        with col3:
            st.button("Esci", key="btn_exit", width="stretch")

        st.divider()
        st.subheader("Ricerca (retriever)")

        # Carica i valori correnti dalla config (SSoT)
        curr_limit, curr_budget_ms, curr_auto = get_retriever_settings()

        # I widget leggono i valori correnti ma NON riscriviamo le loro key in session_state
        new_limit = st.number_input(
            "Candidate limit",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=curr_limit,
            step=500,
            key="retr_limit",
        )
        new_budget_ms = st.number_input(
            "Budget latenza (ms)",
            min_value=0,
            max_value=2000,
            value=curr_budget_ms,
            step=50,
            key="retr_budget",
        )
        new_auto = st.toggle("Auto per budget", value=curr_auto, key="retr_auto")

        # Persisti solo se sono variati; NON toccare le key dei widget in session_state
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

        # Facoltativo: contesto corrente
        if slug:
            st.caption(f"Cliente attivo: **{slug}**")
