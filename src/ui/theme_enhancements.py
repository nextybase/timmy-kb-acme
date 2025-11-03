# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/theme_enhancements.py
from __future__ import annotations

import colorsys
from typing import Callable, Dict

import streamlit as st


def _normalize_hex(color: str | None, fallback: str = "#2B6CB0") -> str:
    raw = (color or "").strip()
    if not raw:
        raw = fallback
    if not raw.startswith("#"):
        raw = f"#{raw}"
    raw = raw.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return fallback.upper()
    try:
        int(raw, 16)
    except ValueError:
        return fallback.upper()
    return f"#{raw.upper()}"


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    base = hex_color.lstrip("#")
    return (
        int(base[0:2], 16) / 255.0,
        int(base[2:4], 16) / 255.0,
        int(base[4:6], 16) / 255.0,
    )


def _lighten(hex_color: str, delta: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    lightness = min(1.0, max(0.0, lightness + delta))
    nr, ng, nb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#{:02X}{:02X}{:02X}".format(int(nr * 255), int(ng * 255), int(nb * 255))


def _relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)

    def _adjust(component: float) -> float:
        if component <= 0.03928:
            return component / 12.92
        return ((component + 0.055) / 1.055) ** 2.4

    r_lin, g_lin, b_lin = (_adjust(r), _adjust(g), _adjust(b))
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def _contrast_color(hex_color: str) -> str:
    """Restituisce il colore del testo (bianco/nero) con contrasto adeguato."""
    return "#111827" if _relative_luminance(hex_color) > 0.6 else "#FFFFFF"


def _resolve_theme_palette() -> Dict[str, str]:
    getter = getattr(st, "get_option", None)
    raw_primary = None
    if callable(getter):
        try:
            raw_primary = getter("theme.primaryColor")
        except Exception:  # pragma: no cover - chiamata opzionale
            raw_primary = None

    primary = _normalize_hex(raw_primary)
    hover = _lighten(primary, delta=0.08)
    active = _lighten(primary, delta=0.16)
    text = _contrast_color(primary)
    return {
        "primary": primary,
        "hover": hover,
        "active": active,
        "text": text,
    }


def _html(fragment: str) -> None:
    injector: Callable[[str], object] | None = getattr(st, "html", None)
    if callable(injector):
        injector(fragment)
        return
    try:
        from streamlit.components.v1 import html as components_html  # type: ignore
    except Exception:
        st.session_state["_theme_css_fragment"] = fragment
        return
    components_html(fragment, height=0)


def inject_theme_css() -> None:
    """Inietta enhancement CSS una sola volta; idempotente per i rerun."""
    if st.session_state.get("_theme_css_injected"):
        return
    st.session_state["_theme_css_injected"] = True

    palette = _resolve_theme_palette()

    css = f"""
    <style id="nexty-theme-enhancements">
      :root{{
        --radius-base: 8px;
        --radius-sm: 6px;
        --focus-ring-light: 0 0 0 3px rgba(43,108,176,.35);
        --focus-ring-dark: 0 0 0 3px rgba(59,130,246,.45);
        --gap-sm: .5rem; --gap-md: .75rem; --gap-lg: 1rem;
        --next-primary: {palette["primary"]};
        --next-primary-hover: {palette["hover"]};
        --next-primary-active: {palette["active"]};
        --next-primary-text: {palette["text"]};
      }}
      html:not([data-theme="dark"]) *:focus {{
        outline: 2px solid transparent !important;
        box-shadow: var(--focus-ring-light) !important;
      }}
      html[data-theme="dark"] *:focus {{
        outline: 2px solid transparent !important;
        box-shadow: var(--focus-ring-dark) !important;
      }}

      [data-testid="stSidebar"] .stButton>button,
      .stButton>button, .stDownloadButton>button,
      .stTextInput input, .stTextArea textarea,
      .stSelectbox div[data-baseweb="select"],
      .stMultiSelect div[data-baseweb="select"],
      .stFileUploader label,
      .stDataFrame, .stTable {{
        border-radius: var(--radius-base) !important;
      }}

      [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: var(--gap-md) !important; }}
      [data-testid="stHorizontalBlock"] {{ gap: var(--gap-md) !important; }}

      a:focus {{ text-decoration: underline !important; }}

      .brand-logo {{
        max-width: 100%;
        height: auto;
        display: block;
      }}

      .brand-logo--sidebar {{
        margin: 0 auto 1rem auto;
      }}

      button[data-testid="baseButton-primary"],
      .stButton>button[kind="primary"],
      .stDownloadButton>button[kind="primary"],
      [data-testid="stSidebar"] .stButton>button[kind="primary"],
      [data-testid="stSidebar"] .stDownloadButton>button[kind="primary"] {{
        background-color: var(--next-primary) !important;
        border-color: var(--next-primary) !important;
        color: var(--next-primary-text) !important;
      }}

      button[data-testid="baseButton-primary"]:hover,
      .stButton>button[kind="primary"]:hover,
      .stDownloadButton>button[kind="primary"]:hover,
      [data-testid="stSidebar"] .stButton>button[kind="primary"]:hover,
      [data-testid="stSidebar"] .stDownloadButton>button[kind="primary"]:hover {{
        background-color: var(--next-primary-hover) !important;
        border-color: var(--next-primary-hover) !important;
        color: var(--next-primary-text) !important;
      }}

      button[data-testid="baseButton-primary"]:active,
      .stButton>button[kind="primary"]:active,
      .stDownloadButton>button[kind="primary"]:active,
      [data-testid="stSidebar"] .stButton>button[kind="primary"]:active,
      [data-testid="stSidebar"] .stDownloadButton>button[kind="primary"]:active {{
        background-color: var(--next-primary-active) !important;
        border-color: var(--next-primary-active) !important;
        color: var(--next-primary-text) !important;
      }}
    </style>
    """
    _html(css)
