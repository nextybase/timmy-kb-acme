# SPDX-License-Identifier: GPL-3.0-or-later
"""Enforcement helpers per la baseline Streamlit di Beta 1.0."""

from __future__ import annotations

from typing import Any

BASELINE_DOC = "docs/policies/streamlit_beta_baseline.md"


def require_streamlit_feature(module: Any, feature: str, *, expect_callable: bool = True) -> Any:
    """Verifica che l'API Streamlit <feature> sia disponibile e, se serve, callable."""

    attr = getattr(module, feature, None)
    if attr is None:
        raise RuntimeError(
            f"Beta 1.0 richiede Streamlit.{feature} (vedi {BASELINE_DOC}) "
            "per garantire comportamenti deterministici."  # noqa: B950 (linea lunga)
        )
    if expect_callable and not callable(attr):
        raise RuntimeError(
            f"Streamlit.{feature} esiste ma non 'callable'; "
            f"assicurati che la versione {BASELINE_DOC} sia installata."
        )
    return attr
