# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/slug.py
from __future__ import annotations

import json
from typing import Any, Optional, cast

from pipeline.logging_utils import get_structured_logger

try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback per ambienti test senza streamlit

    class _StreamlitStub:
        def __init__(self) -> None:
            self.session_state: dict[str, Any] = {}

        def info(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def stop(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("Streamlit non disponibile in questo contesto")

    st = cast(Any, _StreamlitStub())

from pipeline.context import validate_slug
from pipeline.exceptions import ConfigError, InvalidSlug

# Manteniamo compat con l'attuale gestione querystring
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import read_text_safe
from ui.clients_store import get_ui_state_path

from .query_params import get_slug as _qp_get
from .query_params import set_slug as _qp_set

LOGGER = get_structured_logger("ui.slug")


def _has_streamlit_context() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False
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


def _clear_gating_cache() -> None:
    try:
        from ui.gating import reset_gating_cache as _reset  # lazy import per evitare cicli
    except Exception:
        return
    try:
        _reset()
    except Exception:
        pass


def _current_session_slug() -> Optional[str]:
    try:
        return _sanitize_slug(st.session_state.get("__active_slug"))
    except Exception:
        return None


def _set_session_slug(value: Optional[str]) -> None:
    prev = _current_session_slug()
    try:
        st.session_state["__active_slug"] = value
    except Exception:
        if prev != value:
            _clear_gating_cache()
        return
    if prev != value:
        _clear_gating_cache()


def _load_persisted() -> Optional[str]:
    try:
        path = get_ui_state_path()
        raw: Any = json.loads(read_text_safe(path.parent, path))
        if not isinstance(raw, dict):
            return None
        value = raw.get("active_slug")
        return _sanitize_slug(value)  # sanifica anche il persistito
    except Exception:
        return None


def _save_persisted(slug: Optional[str]) -> None:
    try:
        path = get_ui_state_path()
        base_dir = path.parent
        base_dir.mkdir(parents=True, exist_ok=True)
        try:
            current = st.session_state.get("__persisted_slug")
        except Exception:
            current = None
        if current == slug:
            return
        payload = json.dumps({"active_slug": slug or ""}, ensure_ascii=False) + "\n"
        safe_write_text(path, payload, encoding="utf-8", atomic=True)
        try:
            st.session_state["__persisted_slug"] = slug
        except Exception:
            pass
        LOGGER.info("ui.slug.persisted", extra={"path": str(path)})
    except Exception:
        # la UI non deve rompersi per errori di persistenza
        pass


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
        try:
            _qp_set(None)  # rimuovi il param se supportato
        except Exception:
            try:
                _qp_set("")  # fallback: vuoto
            except Exception:
                pass


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
        return ""

    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()
    raise RuntimeError("Streamlit stop should prevent reaching this point")
