# src/ui/utils/query_params.py
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Optional, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback per ambienti test senza streamlit

    class _QueryParams(dict[str, str]):
        pass

    class _StreamlitStub:
        def __init__(self) -> None:
            self.query_params: _QueryParams = _QueryParams()

    st = cast(Any, _StreamlitStub())


QueryParams = MutableMapping[str, Any]


def _query_params() -> QueryParams | None:
    params = getattr(st, "query_params", None)
    if params is None:
        return None
    if isinstance(params, MutableMapping):
        return params
    return cast(QueryParams, params)


def get_slug() -> Optional[str]:
    """
    Legge 'slug' dai query params e lo normalizza.
    Gestisce il caso in cui Streamlit restituisca una lista.
    """
    params = _query_params()
    if params is None:
        return None
    raw = params.get("slug")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, str):
        value = raw.strip().lower()
        return value or None
    return None


def set_slug(slug: Optional[str]) -> None:
    """Imposta o rimuove 'slug' nei query params dopo normalizzazione."""
    params = _query_params()
    if params is None:
        return
    normalized = (slug or "").strip().lower()
    if normalized:
        params["slug"] = normalized
        return

    try:
        del params["slug"]
    except KeyError:
        pass
