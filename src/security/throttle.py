# src/security/throttle.py
from __future__ import annotations

import importlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pipeline.exceptions import RetrieverError

if TYPE_CHECKING:
    try:
        from src.retriever import QueryParams  # type: ignore
    except ImportError:
        try:
            from timmykb.retriever import QueryParams  # type: ignore
        except ImportError:  # pragma: no cover
            from ..retriever import QueryParams

LOGGER = logging.getLogger("security.throttle")

_ENV_IDENTITY_KEYS: tuple[str, ...] = (
    "TIMMY_USER_EMAIL",
    "TIMMY_USER_ID",
    "TIMMY_API_KEY",
    "TIMMY_AUTH_SUB",
)

_SESSION_IDENTITY_KEYS: tuple[str, ...] = (
    "user_email",
    "current_user",
    "email",
    "api_key",
    "user",
)


@dataclass
class _Bucket:
    tokens: float
    updated: float


_BUCKETS: dict[str, _Bucket] = {}
_LOCK = threading.Lock()


def _resolve_identity(default: Optional[str]) -> str:
    identity = _first_env_identity()
    if identity:
        return identity
    identity = _session_identity()
    if identity:
        return identity
    if default:
        LOGGER.debug("throttle.identity.fallback", extra={"identity": default})
        return default
    LOGGER.error("throttle.identity.missing")
    raise RetrieverError("Identità utente non disponibile per la verifica rate limit.")


def _first_env_identity() -> Optional[str]:
    for key in _ENV_IDENTITY_KEYS:
        value = os.environ.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _session_identity() -> Optional[str]:
    try:
        streamlit = importlib.import_module("streamlit")
    except Exception:
        return None
    state = getattr(streamlit, "session_state", None)
    if state is None:
        return None
    for key in _SESSION_IDENTITY_KEYS:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def reset_token_buckets() -> None:
    """Reset dei bucket (utility per test)."""
    with _LOCK:
        _BUCKETS.clear()


def throttle_token_bucket(
    params: "QueryParams",
    *,
    identity: Optional[str] = None,
    max_requests: int = 60,
    interval_seconds: int = 300,
) -> None:
    """Applica un rate limit per-identità con token bucket in-process."""
    if max_requests <= 0 or interval_seconds <= 0:
        raise RetrieverError("Configurazione throttle invalida.")
    user_identity = _resolve_identity(identity or params.project_slug)
    now = time.monotonic()

    with _LOCK:
        bucket = _BUCKETS.get(user_identity)
        if bucket is None:
            bucket = _Bucket(tokens=float(max_requests), updated=now)
            _BUCKETS[user_identity] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated)
            refill = (elapsed / float(interval_seconds)) * float(max_requests)
            bucket.tokens = min(float(max_requests), bucket.tokens + refill)
            bucket.updated = now

        if bucket.tokens < 1.0:
            LOGGER.warning(
                "throttle.denied",
                extra={"identity": user_identity, "max_requests": max_requests, "interval_seconds": interval_seconds},
            )
            raise RetrieverError("Troppe richieste: rate limit superato.")

        bucket.tokens -= 1.0


__all__ = ["throttle_token_bucket", "reset_token_buckets"]
