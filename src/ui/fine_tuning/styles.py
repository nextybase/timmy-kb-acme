# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Callable

from ui.utils.stubs import get_streamlit

st = get_streamlit()


def _html(fragment: str) -> None:
    html_fn: Callable[[str], object] | None = getattr(st, "html", None)
    if callable(html_fn):
        html_fn(fragment)
    else:
        # Se l'API html non è disponibile (es. in test headless) ignora la richiesta.
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
