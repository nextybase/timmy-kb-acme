# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import colorsys
from typing import Callable

from ui.utils.stubs import get_streamlit

st = get_streamlit()


def _normalize_hex(color: str | None, fallback: str = "#2B6CB0") -> str:
    raw = (color or "").strip()
    if not raw:
        raw = fallback
    if not raw.startswith("#"):
        raw = f"#{raw}"
    raw = raw.lstrip("#")
    if len(raw) == 3:  # short form rgb -> rrggbb
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return fallback.upper()
    try:
        int(raw, 16)
    except ValueError:
        return fallback.upper()
    return f"#{raw.upper()}"


def _lighten(hex_color: str, factor: float = 0.12) -> str:
    """Schiarisce il colore preservando la tonalità (fattore 0-1)."""
    base = hex_color.lstrip("#")
    r = int(base[0:2], 16) / 255.0
    g = int(base[2:4], 16) / 255.0
    b = int(base[4:6], 16) / 255.0
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    lightness = min(1.0, max(0.0, lightness + factor))
    nr, ng, nb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#{:02X}{:02X}{:02X}".format(int(nr * 255), int(ng * 255), int(nb * 255))


def _html(fragment: str) -> None:
    html_fn: Callable[[str], object] | None = getattr(st, "html", None)
    if callable(html_fn):
        html_fn(fragment)
    else:
        # Se l'API html non è disponibile (es. in test headless) ignoriamo l'iniezione.
        st.session_state.setdefault("_ft_pending_css", []).append(fragment)


def apply_modal_css() -> None:
    """Inietta uno stile comune per i dialog Streamlit con fallback sicuro."""
    css = """
    <style>
    /* dark overlay */
    [data-testid="stModalOverlay"],
    .stDialogOverlay,
    .stModal {
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background: rgba(0, 0, 0, 0.65) !important;
        z-index: 99998 !important;
    }

    /* centered dialog at 80% width */
    div[role="dialog"][aria-modal="true"] {
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: 80vw !important;
        max-width: 80vw !important;
        max-height: 90vh !important;
        overflow: auto !important;
        border-radius: 12px !important;
        background: #ffffff !important;
        z-index: 99999 !important;
    }

    div[role="dialog"][aria-modal="true"] > div {
        width: 100% !important;
    }

    /* textareas: wider and larger font */
    div[role="dialog"][aria-modal="true"] [data-baseweb="textarea"] {
        width: 100% !important;
        max-width: none !important;
    }

    div[role="dialog"][aria-modal="true"] [data-baseweb="textarea"] textarea,
    div[role="dialog"][aria-modal="true"] textarea {
        width: 100% !important;
        font-size: 1.5em !important;
        line-height: 1.5 !important;
        padding: 12px 14px !important;
        color: #111827 !important;
        font-family: inherit !important;
        box-sizing: border-box !important;
    }
    </style>
    """

    _html(css)


def apply_button_theme() -> None:
    """
    Forza la palette dei pulsanti primari sul colore del tema configurato (idempotente).

    Serve a contrastare eventuali override residuali dovuti al rerender di altre pagine.
    """
    theme_color = None
    try:
        getter = getattr(st, "get_option", None)
        if callable(getter):
            theme_color = getter("theme.primaryColor")
    except Exception:  # pragma: no cover - accesso opzionale
        theme_color = None

    base = _normalize_hex(theme_color)
    hover = _lighten(base, factor=0.10)
    active = _lighten(base, factor=0.18)

    css = f"""
    <style id="tools-check-button-theme">
      :root {{
        --ft-btn-primary: {base};
        --ft-btn-primary-hover: {hover};
        --ft-btn-primary-active: {active};
      }}

      button[data-testid="baseButton-primary"],
      .stButton>button[kind="primary"],
      [data-testid="stSidebar"] .stButton>button[kind="primary"] {{
        background-color: var(--ft-btn-primary) !important;
        border-color: var(--ft-btn-primary) !important;
      }}

      button[data-testid="baseButton-primary"]:hover,
      .stButton>button[kind="primary"]:hover,
      [data-testid="stSidebar"] .stButton>button[kind="primary"]:hover {{
        background-color: var(--ft-btn-primary-hover) !important;
        border-color: var(--ft-btn-primary-hover) !important;
      }}

      button[data-testid="baseButton-primary"]:active,
      .stButton>button[kind="primary"]:active,
      [data-testid="stSidebar"] .stButton>button[kind="primary"]:active {{
        background-color: var(--ft-btn-primary-active) !important;
        border-color: var(--ft-btn-primary-active) !important;
      }}
    </style>
    """

    _html(css)
