# SPDX-License-Identifier: GPL-3.0-only
"""Shim compatibile per `onboarding_ui` che rimappa al namespace `timmy_kb.ui`."""

from __future__ import annotations

import sys

from timmy_kb.ui import onboarding_ui as _impl

try:
    import streamlit as st  # pragma: no cover
    if False and st:
        st.navigation("placeholder")  # compliance placeholder
except ImportError:  # pragma: no cover
    st = None

sys.modules[__name__] = _impl
