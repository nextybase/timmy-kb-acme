# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Tuple

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
        from retriever import MAX_CANDIDATE_LIMIT as _MAX2
        from retriever import MIN_CANDIDATE_LIMIT as _MIN2
        from retriever import _default_candidate_limit as _def_fn

        MIN_CANDIDATE_LIMIT = int(_MIN2)
        MAX_CANDIDATE_LIMIT = int(_MAX2)
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
    """
    Sidebar con azioni rapide e controlli retriever.
    - I valori retriever sono persistiti via ui.config_store.
    - Import "lazy" per evitare errori durante i test/stub.
    """
    # Import lazy della persistenza
    try:
        from ui.config_store import get_retriever_settings, set_retriever_settings
    except Exception:  # pragma: no cover

        def get_retriever_settings() -> Tuple[int, int, bool]:
            return DEFAULT_CANDIDATE_LIMIT, 300, False

        def set_retriever_settings(_limit: int, _budget_ms: int, _auto: bool) -> None:
            return None

    # Carica i valori persistiti e inizializza la sessione al primo giro
    persisted_limit, persisted_budget_ms, persisted_auto = get_retriever_settings()
    st.session_state.setdefault("retr_limit", int(persisted_limit))
    st.session_state.setdefault("retr_budget", int(persisted_budget_ms))
    st.session_state.setdefault("retr_budget_ms", int(persisted_budget_ms))
    st.session_state.setdefault("retr_auto", bool(persisted_auto))

    with st.sidebar:
        st.subheader("Azioni rapide")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.button("Aggiorna Drive", key="btn_refresh", width="stretch")
        with c2:
            st.button("Dummy KB", key="btn_dummy", width="stretch")
        with c3:
            st.button("Esci", key="btn_exit", width="stretch")

        st.divider()
        st.subheader("Ricerca (retriever)")

        new_limit = st.number_input(
            "Candidate limit",
            min_value=MIN_CANDIDATE_LIMIT,
            max_value=MAX_CANDIDATE_LIMIT,
            value=int(st.session_state.get("retr_limit", DEFAULT_CANDIDATE_LIMIT)),
            step=500,
            key="retr_limit",
        )
        new_budget_ms = st.number_input(
            "Budget latenza (ms)",
            min_value=0,
            max_value=2000,
            value=int(st.session_state.get("retr_budget_ms", 300)),
            step=50,
            key="retr_budget_ms",
        )
        new_auto = st.toggle(
            "Auto per budget",
            value=bool(st.session_state.get("retr_auto", False)),
            key="retr_auto",
        )

    # Aggiorna sessione e persistenza se cambiati
    state = st.session_state
    state.update(
        {
            "retr_limit": int(new_limit),
            "retr_budget": int(new_budget_ms),  # compat con chi legge "retr_budget"
            "retr_budget_ms": int(new_budget_ms),  # chiave esplicita con _ms
            "retr_auto": bool(new_auto),
            "slug": slug,
        }
    )

    if (
        int(new_limit) != int(persisted_limit)
        or int(new_budget_ms) != int(persisted_budget_ms)
        or bool(new_auto) != bool(persisted_auto)
    ):
        try:
            set_retriever_settings(int(new_limit), int(new_budget_ms), bool(new_auto))
        except Exception:
            # Non bloccare l'UI se la persistenza fallisce
            pass
