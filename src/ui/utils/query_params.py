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

from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError, InvalidSlug

QueryParams = MutableMapping[str, Any]


def _query_params() -> QueryParams | None:
    params = getattr(st, "query_params", None)
    if params is None:
        return None
    if isinstance(params, MutableMapping):
        return params
    return cast(QueryParams, params)


def _sanitize(slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    try:
        validate_slug(slug)  # può alzare ConfigError (wrappa InvalidSlug)
    except (InvalidSlug, ConfigError):
        return None
    return slug


def get_slug(params: QueryParams | None = None) -> Optional[str]:
    """
    Legge 'slug' dai query params, lo normalizza e lo valida.

    Supporta due modalità:
    - get_slug()                    -> legge da st.query_params
    - get_slug(custom_params_dict)  -> usa il dict passato (utile nei test)
    """
    qp: QueryParams | None = params if params is not None else _query_params()
    if qp is None:
        return None

    raw = qp.get("slug")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, str):
        value = (raw or "").strip().lower()
        return _sanitize(value)
    return None


def set_slug(slug_or_params: Any, maybe_slug: Optional[str] = None) -> None:
    """
    Imposta o rimuove 'slug' nei query params dopo normalizzazione e validazione.

    Supporta due modalità:
    - set_slug(slug)                        -> scrive su st.query_params
    - set_slug(custom_params_dict, slug)    -> scrive sul dict passato (test-friendly)
    """
    # Determina i target dei parametri in modo type-safe per mypy
    params_opt: QueryParams | None
    slug_value: Optional[str]

    if isinstance(slug_or_params, MutableMapping):
        params_opt = cast(QueryParams, slug_or_params)
        slug_value = maybe_slug
    else:
        params_opt = _query_params()
        slug_value = cast(Optional[str], slug_or_params)

    if params_opt is None:
        return

    normalized = _sanitize((slug_value or "").strip().lower())
    if normalized:
        params_opt["slug"] = normalized
        return

    try:
        del params_opt["slug"]
    except KeyError:
        pass
