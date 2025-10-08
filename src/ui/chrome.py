# ui/chrome.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]


def header(slug: Optional[str]) -> None:
    """Header coerente con le regole UI (no unsafe HTML)."""
    st.html("<a id='top'></a>")  # ancorina sicura per skiplink
    st.title("Timmy-KB - Onboarding")
    if slug:
        st.caption(f"Cliente: {slug}")


def sidebar(
    slug: Optional[str],
    *,
    on_refresh: Optional[Callable[[Optional[str]], None]] = None,
    on_generate_dummy: Optional[Callable[[Optional[str]], None]] = None,
    on_exit: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """
    Sidebar con quick actions e controlli retriever.

    Accetta callback opzionali per collegare le azioni alla business logic.
    Ritorna un dizionario con gli stati utili a chi invoca.
    """
    state: Dict[str, Any] = {}

    with st.sidebar:
        st.subheader("Azioni rapide")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Aggiorna Drive", key="btn_refresh", width="stretch"):
                state["refresh_clicked"] = True
                if on_refresh:
                    try:
                        on_refresh(slug)
                    except Exception as exc:
                        st.error(f"Errore refresh: {exc}")
        with col2:
            if st.button("Dummy KB", key="btn_dummy", width="stretch"):
                state["dummy_clicked"] = True
                if on_generate_dummy:
                    try:
                        on_generate_dummy(slug)
                    except Exception as exc:
                        st.error(f"Errore generazione dummy: {exc}")
        with col3:
            if st.button("Esci", key="btn_exit", width="stretch"):
                state["exit_clicked"] = True
                if on_exit:
                    try:
                        on_exit()
                    except Exception as exc:
                        st.error(f"Errore uscita: {exc}")

        st.divider()
        st.subheader("Ricerca (retriever)")
        retr_limit = st.number_input(
            "Candidate limit",
            min_value=500,
            max_value=20000,
            value=4000,
            step=500,
            key="retr_limit",
        )
        retr_budget = st.number_input(
            "Budget latenza (ms)",
            min_value=0,
            max_value=2000,
            value=300,
            step=50,
            key="retr_budget",
        )
        retr_auto = st.toggle("Auto per budget", key="retr_auto")

        state.update(
            {
                "retr_limit": int(retr_limit),
                "retr_budget_ms": int(retr_budget),
                "retr_auto": bool(retr_auto),
                "slug": slug,
            }
        )

    return state
