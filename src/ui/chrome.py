# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import streamlit as st

# --------------------------------------------------------------------------------------
# Limiti retriever (SSoT con fallback sicuro)
# - Se il modulo `retriever` espone le costanti, usiamole.
# - In alternativa, accettiamo una funzione `_default_candidate_limit()` se presente.
# - Fallback hard-coded per non rompere l’UI in assenza del modulo.
# --------------------------------------------------------------------------------------
MIN_CANDIDATE_LIMIT: int = 500
MAX_CANDIDATE_LIMIT: int = 20_000
DEFAULT_CANDIDATE_LIMIT: int = 4_000

try:
    from retriever import DEFAULT_CANDIDATE_LIMIT as _DEF
    from retriever import MAX_CANDIDATE_LIMIT as _MAX
    from retriever import MIN_CANDIDATE_LIMIT as _MIN

    MIN_CANDIDATE_LIMIT = int(_MIN)
    MAX_CANDIDATE_LIMIT = int(_MAX)
    DEFAULT_CANDIDATE_LIMIT = int(_DEF)
except Exception:
    try:
        from retriever import MAX_CANDIDATE_LIMIT as _MAX
        from retriever import MIN_CANDIDATE_LIMIT as _MIN
        from retriever import _default_candidate_limit as _def_fn

        MIN_CANDIDATE_LIMIT = int(_MIN)
        MAX_CANDIDATE_LIMIT = int(_MAX)
        DEFAULT_CANDIDATE_LIMIT = int(_def_fn())
    except Exception:
        # Fallback già valorizzato sopra
        pass


def header(slug: str | None) -> None:
    st.html("<a id='top'></a>")  # ancorina sicura
    st.title("Timmy-KB • Onboarding")
    if slug:
        st.caption(f"Cliente: **{slug}**")


def sidebar(slug: str | None) -> None:
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

        st.number_input(
            "Candidate limit",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=DEFAULT_CANDIDATE_LIMIT,
            step=500,  # se in futuro il retriever espone anche uno STEP, possiamo allinearlo qui
            key="retr_limit",
        )
        st.number_input("Budget latenza (ms)", min_value=0, max_value=2000, value=300, step=50, key="retr_budget")
        st.toggle("Auto per budget", key="retr_auto")
