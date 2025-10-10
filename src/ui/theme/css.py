# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from textwrap import dedent
from typing import Any

from . import tokens as T


def inject_theme_css(st_module: Any) -> None:
    """Inietta il CSS del brand una sola volta per sessione."""
    if getattr(st_module.session_state, "_theme_css_injected", False):
        return

    css = f"""
    /* ====== NeXT.AI Theme (Streamlit) ====== */
    :root {{
      --brand-text: {T.COLOR_TEXT};
      --brand-bg: {T.COLOR_BG};
      --brand-dark: {T.COLOR_DARK};
      --brand-accent: {T.COLOR_ACCENT};
      --brand-link: {T.COLOR_LINK};
      --brand-ocean: {T.COLOR_OCEAN};
      --radius-m: {T.RADIUS_M}px;
    }}

    /* Font */
    @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@300;500&display=swap');
    html, body, .stApp {{ font-family: {T.FONT_FAMILY} !important; }}

    /* Titoli */
    h1, .stMarkdown h1 {{ font-weight: 500; letter-spacing: -0.5px; font-size: {T.H1_SIZE_PX}px; }}
    h2, .stMarkdown h2 {{ font-weight: 500; }}

    /* Link */
    a, .stMarkdown a {{ color: var(--brand-link); text-decoration: none; }}
    a:hover, .stMarkdown a:hover {{ text-decoration: underline; }}

    /* Pulsanti nativi */
    .stButton>button, .stLinkButton>button {{
      border-radius: var(--radius-m);
      box-shadow: inset 0 1px {T.INSET_HIGHLIGHT};
    }}
    .stButton>button {{ background: var(--brand-dark); color: #fff; }}
    .stButton>button:hover {{ background: var(--brand-accent); color: var(--brand-dark); }}

    /* Link button full width */
    .stLinkButton>button {{ width: 100%; }}

    /* Focus (accessibile) */
    *:focus {{ outline: 3px solid var(--brand-link) !important; outline-offset: 4px; border-radius: 5px; }}
    """

    st_module.html(f"<style>{dedent(css)}</style>")
    theme_base = None
    getter = getattr(st_module, "get_option", None)
    if callable(getter):
        try:
            raw_base = getter("theme.base")
            if isinstance(raw_base, str) and raw_base.strip():
                theme_base = raw_base.strip().lower()
        except Exception:
            theme_base = None
    if theme_base:
        st_module.session_state["_ui_theme_base"] = theme_base

    st_module.session_state._theme_css_injected = True
