# src/security/authorization.py
from __future__ import annotations

import importlib
import logging
import os
from typing import TYPE_CHECKING, Iterable, Optional

from pipeline.exceptions import RetrieverError

if TYPE_CHECKING:
    from src.retriever import QueryParams

LOGGER = logging.getLogger("security.authorization")

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
    LOGGER.error("authorization.active_slug.missing")
    raise RetrieverError("Slug attivo non disponibile per l'autorizzazione della ricerca.")


def authorizer_session(params: "QueryParams") -> None:
    """Consente la ricerca solo se lo slug coincide con quello del contesto attivo."""
    active_slug = _resolve_active_slug()
    if params.project_slug.strip() != active_slug:
        LOGGER.warning(
            "authorization.denied",
            extra={
                "expected_slug": active_slug,
                "received_slug": params.project_slug,
            },
        )
        raise RetrieverError("Accesso alla ricerca negato per slug non autorizzato.")
