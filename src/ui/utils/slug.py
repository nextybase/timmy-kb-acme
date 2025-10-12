# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/slug.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# Manteniamo compat con l'attuale gestione querystring
from pipeline.path_utils import read_text_safe
from ui.utils.query_params import get_slug as _qp_get
from ui.utils.query_params import set_slug as _qp_set

_PERSIST_PATH = Path(__file__).resolve().parents[2] / "clients_db" / "ui_state.json"


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


def _load_persisted() -> Optional[str]:
    try:
        raw: Any = json.loads(read_text_safe(_PERSIST_PATH.parent, _PERSIST_PATH))
        if not isinstance(raw, dict):
            return None
        value = raw.get("active_slug")
        return _normalize_slug(value)
    except Exception:
        return None


def _save_persisted(slug: Optional[str]) -> None:
    try:
        _PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PERSIST_PATH.open("w", encoding="utf-8") as fh:
            json.dump({"active_slug": slug or ""}, fh)
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
    s = _normalize_slug(_qp_get())
    if s:
        st.session_state["__active_slug"] = s
        _save_persisted(s)
        return s

    s = _normalize_slug(st.session_state.get("__active_slug"))
    if s:
        _qp_set(s)  # riallinea la query
        return s

    s = _load_persisted()
    if s:
        st.session_state["__active_slug"] = s
        _qp_set(s)
        return s

    return None


def set_active_slug(slug: Optional[str], *, persist: bool = True, update_query: bool = True) -> None:
    s = _normalize_slug(slug)
    st.session_state["__active_slug"] = s
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
