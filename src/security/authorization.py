# path: src/security/authorization.py
from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING, Iterable, Optional

from pipeline.exceptions import RetrieverError
from pipeline.logging_utils import get_structured_logger

if TYPE_CHECKING:
    try:
        from src.retriever import QueryParams  # type: ignore
    except ImportError:
        try:
            from timmykb.retriever import QueryParams  # type: ignore
        except ImportError:  # pragma: no cover
            from ..retriever import QueryParams

LOGGER = get_structured_logger("security.authorization", propagate=False)

_ENV_SLUG_KEYS: tuple[str, ...] = (
    "TIMMY_ACTIVE_SLUG",
    "TIMMY_KB_ACTIVE_SLUG",
    "PROJECT_SLUG",
)

_SESSION_KEYS: tuple[str, ...] = (
    "active_slug",
    "project_slug",
    "client_slug",
    "slug",
)


def _first_non_empty(values: Iterable[Optional[str]]) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _slug_from_environment() -> Optional[str]:
    return _first_non_empty(os.environ.get(key) for key in _ENV_SLUG_KEYS)


def _slug_from_streamlit_session() -> Optional[str]:
    try:
        streamlit = importlib.import_module("streamlit")
    except Exception:
        return None
    session_state = getattr(streamlit, "session_state", None)
    if session_state is None:
        return None
    return _first_non_empty(session_state.get(key) for key in _SESSION_KEYS)


def _resolve_active_slug() -> str:
    slug = _slug_from_environment()
    if slug:
        return slug
    slug = _slug_from_streamlit_session()
    if slug:
        return slug
    LOGGER.error("authorization.active_slug.missing", extra={"event": "authorization.active_slug.missing"})
    raise RetrieverError("Slug attivo non disponibile per l'autorizzazione della ricerca.")


def authorizer_session(params: "QueryParams") -> None:
    """Consente la ricerca solo se lo slug coincide con quello del contesto attivo."""
    active_slug = _resolve_active_slug()
    # Hardening: confronto normalizzato
    req_slug_norm = params.project_slug.strip().lower()
    active_slug_norm = active_slug.strip().lower()
    if req_slug_norm != active_slug_norm:
        LOGGER.warning(
            "authorization.denied",
            extra={
                "event": "authorization.denied",
                "expected_slug": active_slug_norm,
                "received_slug": req_slug_norm,
            },
        )
        raise RetrieverError("Accesso alla ricerca negato per slug non autorizzato.")


__all__ = ["authorizer_session"]
