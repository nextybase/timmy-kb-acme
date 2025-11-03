# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/theme_enhancements.py
from __future__ import annotations

import streamlit as st


def inject_theme_css() -> None:
    """
    Mantiene compatibilità con le chiamate esistenti senza applicare override CSS.

    L'interfaccia utilizzerà esclusivamente lo styling nativo di Streamlit,
    basandosi sui valori definiti in `.streamlit/config.toml`.
    """
    st.session_state.setdefault("_theme_css_injected", True)


__all__ = ["inject_theme_css"]
