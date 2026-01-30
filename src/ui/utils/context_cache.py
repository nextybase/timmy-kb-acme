# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sys
from typing import Any, Dict, Optional, cast

from pipeline.context import ClientContext

st: Any | None = None
_CACHE_KEY = "_client_context_cache"
_DEFAULT_RUN_KEY = "__default__"


def _cache_key(normalized_slug: str, require_drive_env: bool, run_id: str | None) -> str:
    """Costruisce la chiave di cache includendo run_id per distinguere i contesti."""
    run_marker = run_id or _DEFAULT_RUN_KEY
    return f"{normalized_slug}|{int(require_drive_env)}|{run_marker}"


def _get_cache() -> Optional[Dict[str, ClientContext]]:
    if st is not None:
        session_state = getattr(st, "session_state", None)
    elif "streamlit" in sys.modules:
        from ui.utils.stubs import get_streamlit

        st_module = get_streamlit()
        session_state = getattr(st_module, "session_state", None) if st_module is not None else None
    else:
        return None
    if session_state is None:
        return None
    cache = cast(Optional[Dict[str, ClientContext]], session_state.get(_CACHE_KEY))
    if isinstance(cache, dict):
        return cache
    cache = {}
    session_state[_CACHE_KEY] = cache
    return cache


def get_client_context(
    slug: str,
    *,
    require_drive_env: bool = False,
    run_id: str | None = None,
    force_reload: bool = False,
) -> ClientContext:
    """Ritorna il ClientContext per lo slug, cacheando in sessione Streamlit quando disponibile."""
    normalized = (slug or "").strip().lower()
    cache = _get_cache()
    cache_key = _cache_key(normalized, require_drive_env, run_id)

    cached_ctx = cache.get(cache_key) if cache and not force_reload else None
    if cached_ctx is not None:
        return cached_ctx

    # Se forziamo il reload o non esiste cache entry, rimuoviamo eventuali precedenti.
    if cache is not None:
        cache.pop(cache_key, None)

    ctx = ClientContext.load(
        slug=slug,
        require_drive_env=require_drive_env,
        run_id=run_id,
    )
    if cache is not None:
        cache[cache_key] = ctx
    return ctx


def invalidate_client_context(slug: str | None = None) -> None:
    """Invalida la cache sessione del ClientContext (per uno slug o completamente)."""
    cache = _get_cache()
    if cache is None:
        return
    if slug:
        normalized = slug.strip().lower()
        keys = [key for key in list(cache.keys()) if key.startswith(f"{normalized}|")]
        for key in keys:
            cache.pop(key, None)
    else:
        cache.clear()


__all__ = ["get_client_context", "invalidate_client_context"]
