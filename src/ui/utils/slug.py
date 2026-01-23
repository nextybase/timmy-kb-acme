# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/slug.py
from __future__ import annotations

import json
from typing import Any, Optional

import streamlit as st

from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError, InvalidSlug

# Manteniamo l'attuale gestione querystring
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe
from ui.clients_store import get_ui_state_path

from .query_params import get_slug as _qp_get
from .query_params import set_slug as _qp_set

LOGGER = get_structured_logger("ui.slug")
_PERSIST_UNAVAILABLE_LOGGED = False
_RUNTIME_SLUG_RESOLVE_GUARD = False


def _has_streamlit_context() -> bool:
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    return get_script_run_ctx() is not None


def _normalize_slug(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    slug = value.strip().lower()
    return slug or None


def _sanitize_slug(value: Any) -> Optional[str]:
    slug = _normalize_slug(value)
    if not slug:
        return None
    try:
        validate_slug(slug)  # può alzare ConfigError (wrappa InvalidSlug)
    except (InvalidSlug, ConfigError):
        LOGGER.warning("ui.slug.invalid", extra={"slug": slug})
        return None
    return slug


def _slug_in_registry(slug: str) -> bool:
    try:
        from ui.clients_store import get_all as _get_all
    except Exception as exc:
        LOGGER.warning("ui.slug.registry_load_failed", exc_info=exc)
        return False
    try:
        for entry in _get_all():
            try:
                if entry.slug.strip().lower() == slug:
                    return True
            except Exception:
                continue
    except Exception as exc:
        LOGGER.warning("ui.slug.registry_scan_failed", exc_info=exc)
        return False
    return False


def _clear_gating_cache() -> None:
    try:
        from ui.gating import reset_gating_cache as _reset  # lazy import per evitare cicli
    except Exception as exc:
        LOGGER.warning("ui.slug.gating_reset_import_failed", exc_info=exc)
        return
    try:
        _reset()
    except Exception as exc:
        LOGGER.warning("ui.slug.gating_reset_failed", exc_info=exc)


def _current_session_slug() -> Optional[str]:
    try:
        return _sanitize_slug(st.session_state.get("__active_slug"))
    except Exception as exc:
        LOGGER.warning("ui.slug.session_read_failed", exc_info=exc)
        return None


def _set_session_slug(value: Optional[str]) -> None:
    prev = _current_session_slug()
    try:
        st.session_state["__active_slug"] = value
    except Exception as exc:
        LOGGER.warning("ui.slug.session_write_failed", extra={"prev": prev, "value": value}, exc_info=exc)
        if prev != value:
            _clear_gating_cache()
        return
    if prev != value:
        _clear_gating_cache()


def _load_persisted() -> Optional[str]:
    try:
        path = get_ui_state_path()
    except ConfigError as exc:
        _log_persist_unavailable_once(exc)
        return None
    try:
        raw_text = read_text_safe(path.parent, path)
        raw: Any = json.loads(raw_text)
        if not isinstance(raw, dict):
            return None
        value = raw.get("active_slug")
        slug = _sanitize_slug(value)  # sanifica anche il persistito
        if slug and not _slug_in_registry(slug):
            LOGGER.info("ui.slug.persist_ignored", extra={"slug": slug, "reason": "not_in_registry"})
            return None
        return slug
    except Exception as exc:
        LOGGER.warning("ui.slug.persist_load_failed", extra={"path": str(path)}, exc_info=exc)
        return None


def get_runtime_slug() -> Optional[str]:
    """
    Risolve lo slug runtime in modo deterministico (senza side-effect).
    Ordine: query params, session_state, persisted state.
    """
    try:
        slug = _sanitize_slug(_qp_get())
    except Exception:
        slug = None
    if slug:
        return slug
    slug = _current_session_slug()
    if slug:
        return slug
    global _RUNTIME_SLUG_RESOLVE_GUARD
    if _RUNTIME_SLUG_RESOLVE_GUARD:
        return None
    try:
        _RUNTIME_SLUG_RESOLVE_GUARD = True
        return _load_persisted()
    finally:
        _RUNTIME_SLUG_RESOLVE_GUARD = False


def _log_persist_unavailable_once(exc: ConfigError) -> None:
    global _PERSIST_UNAVAILABLE_LOGGED
    try:
        if st.session_state.get("__persist_unavailable_logged"):
            return
        st.session_state["__persist_unavailable_logged"] = True
    except Exception:
        if _PERSIST_UNAVAILABLE_LOGGED:
            return
        _PERSIST_UNAVAILABLE_LOGGED = True
    LOGGER.debug("ui.slug.persist_unavailable", extra={"code": getattr(exc, "code", None)})


def _save_persisted(slug: Optional[str]) -> None:
    try:
        path = get_ui_state_path()
    except ConfigError as exc:
        _log_persist_unavailable_once(exc)
        return
    try:
        base_dir = path.parent
        base_dir.mkdir(parents=True, exist_ok=True)
        try:
            current = st.session_state.get("__persisted_slug")
        except Exception as exc:
            LOGGER.debug("ui.slug.persist_session_read_failed", exc_info=exc)
            current = None
        if current == slug:
            return
        payload = json.dumps({"active_slug": slug or ""}, ensure_ascii=False) + "\n"
        safe_write_text(path, payload, encoding="utf-8", atomic=True)
        try:
            st.session_state["__persisted_slug"] = slug
        except Exception as exc:
            LOGGER.debug("ui.slug.persist_session_write_failed", extra={"slug": slug}, exc_info=exc)
        LOGGER.info("ui.slug.persisted", extra={"path": str(path)})
    except Exception as exc:
        # la UI non deve rompersi per errori di persistenza
        LOGGER.error("ui.slug.persist_failed", extra={"path": str(path), "slug": slug}, exc_info=exc)


def get_active_slug() -> Optional[str]:
    """
    Ordine di risoluzione:
    1) query param 'slug'
    2) st.session_state['__active_slug']
    3) clients_db/ui_state.json
    Se trovato, riallinea sempre gli altri layer.
    """
    # lettura da query/sessione…
    s = _sanitize_slug(_qp_get())
    if s:
        _set_session_slug(s)
        _save_persisted(s)
        return s

    s = _sanitize_slug(st.session_state.get("__active_slug"))
    if s:
        _qp_set(s)  # riallinea la query
        return s

    s = _load_persisted()
    if s:
        _set_session_slug(s)
        _qp_set(s)
        return s

    return None


def set_active_slug(slug: Optional[str], *, persist: bool = True, update_query: bool = True) -> None:
    # set attivo…
    s = _sanitize_slug(slug)
    _set_session_slug(s)
    if persist:
        _save_persisted(s)
    if update_query:
        _qp_set(s or None)


def clear_active_slug(*, persist: bool = True, update_query: bool = True) -> None:
    """
    Azzera lo slug attivo su tutti i layer:
    - session_state
    - persistenza (clients_db/ui_state.json)
    - querystring (?slug)
    """
    # 1) session
    _set_session_slug(None)
    st.session_state.pop("__active_slug", None)
    # 2) persistenza
    if persist:
        _save_persisted("")
    # 3) querystring
    if update_query:
        _qp_set(None)


# alias comodo
def clear_slug() -> None:
    clear_active_slug()


def require_active_slug() -> str:
    """
    Restituisce lo slug attivo o blocca la pagina con un messaggio.
    Da usare a inizio pagina (tranne new_client.py).
    """
    slug = get_active_slug()
    if slug:
        return slug

    if not _has_streamlit_context():
        raise RuntimeError("Streamlit runtime non attivo: impossibile risolvere lo slug in UI.")

    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()
    raise RuntimeError("Streamlit stop should prevent reaching this point")
