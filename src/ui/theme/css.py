# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from textwrap import dedent
from typing import Any

from ui.utils.core import get_theme_base  # nuovo import

from . import tokens as T


def inject_theme_css(st_module: Any) -> None:
    """
    Inietta il CSS del brand. Se la base del tema cambia (light/dark),
    forza una nuova iniezione.
    """
    base = get_theme_base()
    # Se il tema è cambiato rispetto al precedente, invalida la cache di iniezione
    prev = st_module.session_state.get("_ui_theme_base")
    if prev != base:
        st_module.session_state["_theme_css_injected"] = False

    if st_module.session_state.get("_theme_css_injected", False):
        return

    TT = T.resolve_tokens(base)

    css = f"""
    /* ====== NeXT.AI Theme (Streamlit) ====== */
    :root {{
      --brand-text: {TT.COLOR_TEXT};
      --brand-bg: {TT.COLOR_BG};
      --brand-dark: {TT.COLOR_DARK};
      --brand-accent: {TT.COLOR_ACCENT};
      --brand-link: {TT.COLOR_LINK};
      --brand-ocean: {TT.COLOR_OCEAN};
      --radius-m: {TT.RADIUS_M}px;
    }}

    /* Font */
    @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;500&display=swap');
    html, body, .stApp {{
      font-family: {TT.FONT_FAMILY} !important;
      background: var(--brand-bg);
      color: var(--brand-text);
    }}

    /* Titoli */
    h1, .stMarkdown h1 {{ font-weight: 500; letter-spacing: -0.5px; font-size: {TT.H1_SIZE_PX}px; }}
    h2, .stMarkdown h2 {{ font-weight: 500; }}

    /* Link */
    a, .stMarkdown a {{ color: var(--brand-link); text-decoration: none; }}
    a:hover, .stMarkdown a:hover {{ text-decoration: underline; }}

    /* Pulsanti nativi */
    .stButton>button, .stLinkButton>button {{
      border-radius: var(--radius-m);
      box-shadow: inset 0 1px {TT.INSET_HIGHLIGHT};
    }}
    /* default (secondary) */
    .stButton>button[data-testid="baseButton-secondary"] {{
      background: var(--brand-dark); color: #fff; border: none;
    }}
    .stButton>button[data-testid="baseButton-secondary"]:hover {{
      background: var(--brand-accent); color: var(--brand-dark);
    }}
    /* primary = arancione (usato per "Esci") */
    .stButton>button[data-testid="baseButton-primary"] {{
      background: var(--brand-accent); color: var(--brand-dark); border: none;
    }}
    .stButton>button[data-testid="baseButton-primary"]:hover {{
      filter: brightness(0.95);
    }}

    /* Link button full width */
    .stLinkButton>button {{ width: 100%; }}

    /* Focus (accessibile) */
    *:focus {{ outline: 3px solid var(--brand-link) !important; outline-offset: 4px; border-radius: 5px; }}
    """

    st_module.html(f"<style>{dedent(css)}</style>")
    st_module.session_state["_ui_theme_base"] = base
    st_module.session_state["_theme_css_injected"] = True
