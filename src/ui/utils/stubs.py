# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/stubs.py
from __future__ import annotations

from typing import Any


def get_streamlit() -> Any:
    """Restituisce il modulo streamlit (contrattuale nel runtime Beta 1.0)."""
    import streamlit as st

    return st


__all__ = ["get_streamlit"]
