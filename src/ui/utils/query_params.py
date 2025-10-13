# src/ui/utils/query_params.py
from __future__ import annotations

from typing import Any, List, Optional, Union, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback per ambienti test senza streamlit

    class _QueryParams(dict[str, str]):
        pass

    class _StreamlitStub:
        def __init__(self) -> None:
            self.query_params: _QueryParams = _QueryParams()

    st = cast(Any, _StreamlitStub())


def get_slug() -> Optional[str]:
    """
    Legge 'slug' dai query params e lo normalizza.
    Gestisce il caso in cui Streamlit restituisca una lista.
    """
    raw: Union[str, List[str], None] = st.query_params.get("slug")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, str):
        value = raw.strip().lower()
        return value or None
    return None


def set_slug(slug: Optional[str]) -> None:
    """Imposta o rimuove 'slug' nei query params dopo normalizzazione."""
    normalized = (slug or "").strip().lower()
    if normalized:
        st.query_params["slug"] = normalized
        return

    try:
        del st.query_params["slug"]
    except KeyError:
        pass
