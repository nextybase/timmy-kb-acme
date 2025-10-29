# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/theme_enhancements.py
from __future__ import annotations

import streamlit as st


def _html(fragment: str) -> None:
    injector = getattr(st, "html", None)
    if callable(injector):
        injector(fragment)
        return
    try:
        from streamlit.components.v1 import html as components_html
    except Exception:
        st.session_state["_theme_css_fragment"] = fragment
        return
    components_html(fragment, height=0)


def inject_theme_css() -> None:
    """Inietta enhancement CSS una sola volta; idempotente per i rerun."""
    if st.session_state.get("_theme_css_injected"):
        return
    st.session_state["_theme_css_injected"] = True

    css = """
    <style id="nexty-theme-enhancements">
      :root{
        --radius-base: 8px;
        --radius-sm: 6px;
        --focus-ring-light: 0 0 0 3px rgba(43,108,176,.35);
        --focus-ring-dark: 0 0 0 3px rgba(59,130,246,.45);
        --gap-sm: .5rem; --gap-md: .75rem; --gap-lg: 1rem;
      }
      html:not([data-theme="dark"]) *:focus {
        outline: 2px solid transparent !important;
        box-shadow: var(--focus-ring-light) !important;
      }
      html[data-theme="dark"] *:focus {
        outline: 2px solid transparent !important;
        box-shadow: var(--focus-ring-dark) !important;
      }

      [data-testid="stSidebar"] .stButton>button,
      .stButton>button, .stDownloadButton>button,
      .stTextInput input, .stTextArea textarea,
      .stSelectbox div[data-baseweb="select"],
      .stMultiSelect div[data-baseweb="select"],
      .stFileUploader label,
      .stDataFrame, .stTable {
        border-radius: var(--radius-base) !important;
      }

      [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: var(--gap-md) !important; }
      [data-testid="stHorizontalBlock"] { gap: var(--gap-md) !important; }

      a:focus { text-decoration: underline !important; }
    </style>
    """
    _html(css)
