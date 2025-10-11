# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from textwrap import dedent
from typing import Any

from ui.utils.core import get_theme_base  # resta valido

from . import tokens as T


def _current_base(st_module: Any) -> str:
    base: str = get_theme_base()
    st_module.session_state["brand_theme"] = base
    return base


def inject_theme_css(st_module: Any) -> None:
    """
    Inietta CSS brand UNA SOLA VOLTA con entrambe le palette.
    Ad ogni chiamata riallinea l'attributo DOM data-brand-theme.
    """
    base = _current_base(st_module)

    if not st_module.session_state.get("_theme_css_injected", False):
        L = T.resolve_tokens("light")
        D = T.resolve_tokens("dark")

        css = f"""
        /* ====== NeXT.AI Theme ====== */
        :root {{
          /* LIGHT */
          --light-text: {L.COLOR_TEXT};
          --light-bg: {L.COLOR_BG};
          --light-dark: {L.COLOR_DARK};
          --light-accent: {L.COLOR_ACCENT};
          --light-link: {L.COLOR_LINK};
          --light-ocean: {L.COLOR_OCEAN};
          /* DARK */
          --dark-text: {D.COLOR_TEXT};
          --dark-bg: {D.COLOR_BG};
          --dark-dark: {D.COLOR_DARK};
          --dark-accent: {D.COLOR_ACCENT};
          --dark-link: {D.COLOR_LINK};
          --dark-ocean: {D.COLOR_OCEAN};
          --radius-m: {L.RADIUS_M}px;
        }}

        :root[data-brand-theme='light'] {{
          --brand-text: var(--light-text);
          --brand-bg: var(--light-bg);
          --brand-dark: var(--light-dark);
          --brand-accent: var(--light-accent);
          --brand-link: var(--light-link);
          --brand-ocean: var(--light-ocean);
        }}
        :root[data-brand-theme='dark'] {{
          --brand-text: var(--dark-text);
          --brand-bg: var(--dark-bg);
          --brand-dark: var(--dark-dark);
          --brand-accent: var(--dark-accent);
          --brand-link: var(--dark-link);
          --brand-ocean: var(--dark-ocean);
        }}

        @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;500&display=swap');
        html, body, .stApp {{ font-family: {L.FONT_FAMILY} !important; }}

        .stButton>button, .stLinkButton>button {{
          border-radius: var(--radius-m);
          box-shadow: inset 0 1px {L.INSET_HIGHLIGHT};
        }}
        .stButton>button[data-testid="baseButton-secondary"] {{
          background: var(--brand-dark); color: #fff; border: none;
        }}
        .stButton>button[data-testid="baseButton-secondary"]:hover {{
          background: var(--brand-accent); color: var(--brand-dark);
        }}
        .stButton>button[data-testid="baseButton-primary"] {{
          background: var(--brand-accent); color: var(--brand-dark); border: none;
        }}
        .stButton>button[data-testid="baseButton-primary"]:hover {{ filter: brightness(0.95); }}

        a, .stMarkdown a {{ color: var(--brand-link); text-decoration: none; }}
        a:hover, .stMarkdown a:hover {{ text-decoration: underline; }}

        h1, .stMarkdown h1 {{ font-weight: 500; letter-spacing: -0.5px; font-size: {L.H1_SIZE_PX}px; }}
        h2, .stMarkdown h2 {{ font-weight: 500; }}

        *:focus {{ outline: 3px solid var(--brand-link) !important; outline-offset: 4px; border-radius: 5px; }}
        """
        st_module.html(f"<style>{dedent(css)}</style>")
        st_module.session_state["_theme_css_injected"] = True

    # Aggiorna SEMPRE l'attributo DOM + registro base corrente
    st_module.html(f"<script>document.documentElement.setAttribute('data-brand-theme','{base}');</script>")
    st_module.session_state["_ui_theme_base"] = base
