# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

# SSoT: limiti e persistenza retriever
from ui.config_store import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, get_retriever_settings, set_retriever_settings
from ui.landing_slug import _request_shutdown as _shutdown  # deterministico
from ui.theme.css import inject_theme_css
from ui.utils.branding import get_favicon_path, render_brand_header, render_sidebar_brand

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ----------
def _on_dummy_kb() -> None:
    st.session_state["dummy_kb_requested"] = True
    st.toast("Dummy KB richiesta. Vai su Gestisci cliente per verificare.")


def _on_exit() -> None:
    _shutdown(None)  # compat con firma (_request_shutdown(log))


def _current_theme() -> str:
    """Preferenza tema (light|dark) in sessione; default light."""
    return st.session_state.get("brand_theme", "light")


# ---------- layout ----------
def header(slug: str | None) -> None:
    """Header con branding (favicon, titolo, sottotitolo). Logo SOLO in sidebar."""
    # set_page_config deve essere il primissimo output
    try:
        st.set_page_config(
            page_title="Timmy-KB • Onboarding",
            layout="wide",
            page_icon=str(get_favicon_path(REPO_ROOT)),
        )
    except Exception:
        # già impostato in un altro punto o in un rerun
        pass

    # Inietta skin brand (Lexend, palette, pulsanti, focus) secondo tema scelto
    theme = _current_theme()
    os.environ["TIMMY_UI_BRAND_THEME"] = theme  # per logo dark/light nei resolver
    inject_theme_css(st)

    subtitle = f"Cliente: {slug}" if slug else "Nuovo cliente"
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,  # logo nel main disabilitato: solo in sidebar
    )


def sidebar(slug: str | None) -> None:
    """Sidebar con brand, azioni rapide, toggle tema e settaggi retriever."""
    with st.sidebar:
        # Logo compatto tema-aware
        render_sidebar_brand(st_module=st, repo_root=REPO_ROOT)

        st.subheader("Azioni rapide")

        # Toggle tema (light <-> dark)
        theme = _current_theme()
        label = "Tema: 🌙 Dark" if theme == "light" else "Tema: ☀️ Light"
        if st.button(label, key="btn_toggle_theme", help="Cambia tema", width="stretch"):
            st.session_state["brand_theme"] = "dark" if theme == "light" else "light"
            os.environ["TIMMY_UI_BRAND_THEME"] = st.session_state["brand_theme"]
            st.rerun()

        # Guida UI full-width (niente 'Aggiorna Drive')
        st.link_button(
            "Guida UI",
            url="https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md",
            width="stretch",
        )

        if st.button("Dummy KB", key="btn_dummy", width="stretch"):
            _on_dummy_kb()
        if st.button("Esci", key="btn_exit", width="stretch"):
            _on_exit()

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
