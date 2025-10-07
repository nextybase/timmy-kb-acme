"""Tab Semantica UI."""

from __future__ import annotations

import logging

from src.ui.app_core.logging import _setup_logging

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def render_semantics(*, slug: str | None, logger: logging.Logger | None = None) -> None:
    """Tab Semantica: conversione RAW->BOOK e materiali correlati."""
    log = logger or _setup_logging()
    if st is None:
        return
    slug_value = (slug or st.session_state.get("ui.manage.selected_slug") or "").strip()
    if not slug_value:
        st.info("Seleziona prima un cliente per accedere alla sezione Semantica.")
        return
    try:
        from ui.tabs.semantic import render_semantic_tab
    except Exception as exc:  # pragma: no cover
        log.warning("ui.tabs.semantic_import_failed", extra={"slug": slug_value, "error": str(exc)})
        return
    render_semantic_tab(log=log, slug=slug_value)


# TEST: ruff check .
# TEST: streamlit run onboarding_ui.py
