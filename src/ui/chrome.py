# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.landing_slug import _request_shutdown as _shutdown  # deterministico
from ui.theme.css import inject_theme_css
from ui.utils.branding import render_brand_header, render_sidebar_brand

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ----------
def _on_dummy_kb() -> None:
    st.session_state["dummy_kb_requested"] = True
    st.toast("Dummy KB richiesta. Vai su Gestisci cliente per verificare.")


def _on_exit() -> None:
    _shutdown(None)  # compat con firma (_request_shutdown(log))


# ---------- layout ----------
def header(slug: str | None) -> None:
    """
    Header della UI.
    Nota: l'unica chiamata a `st.set_page_config(...)` deve stare nell'entrypoint
    (onboarding_ui.py). Qui iniettiamo solo il CSS brand e rendiamo l'header.
    """
    # CSS brand early-inject (tema gestito nativamente da Streamlit)
    inject_theme_css(st)

    subtitle = f"Cliente: {slug}" if slug else "Nuovo cliente"
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,
    )


def sidebar(slug: str | None) -> None:
    """Sidebar con brand e azioni rapide."""
    with st.sidebar:
        # Logo compatto tema-aware
        render_sidebar_brand(st_module=st, repo_root=REPO_ROOT)

        st.subheader("Azioni rapide")

        # Guida UI full-width
        st.link_button(
            "Guida UI",
            url="https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md",
            width="stretch",
        )

        if st.button("Dummy KB", key="btn_dummy", width="stretch"):
            _on_dummy_kb()
        if st.button("Esci", key="btn_exit", type="primary", width="stretch"):
            _on_exit()

        # Facoltativo: contesto corrente
        if slug:
            st.caption(f"Cliente attivo: **{slug}**")
