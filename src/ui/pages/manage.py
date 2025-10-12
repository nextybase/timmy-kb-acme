# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import require_active_slug


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione se disponibile, altrimenti None. Formato: 'pkg.mod:func'."""
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Services (gestiscono cache e bridging verso i component)
_render_drive_tree = _safe_get("ui.services.drive:render_drive_tree")
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")
_emit_readmes_for_raw = _safe_get("ui.services.drive_runner:emit_readmes_for_raw")

# Tool di pulizia workspace (locale + DB + Drive)
# run_cleanup(slug: str, assume_yes: bool = False) -> int
_run_cleanup = _safe_get("src.tools.clean_client_workspace:run_cleanup")


# ---------------- UI ----------------

slug = require_active_slug()

header(slug)
sidebar(slug)

# Da qui in poi: slug presente → viste operative
col_left, col_right = st.columns(2)

with col_left:
    if _render_drive_tree is not None:
        try:
            _render_drive_tree(slug)  # restituisce anche indice cachato
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Drive: {e}")
    else:
        st.info("Vista Drive non disponibile.")

with col_right:
    if _render_drive_diff is not None:
        try:
            _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Diff: {e}")
    else:
        st.info("Vista Diff non disponibile.")

    # --- Azione: Genera README nelle cartelle raw/ (sempre visibile) ---
    st.markdown("")
    if st.button("Genera README in raw/ (Drive)", key="btn_emit_readmes", width="stretch"):
        if _emit_readmes_for_raw is None:
            st.error(
                "Funzione non disponibile. Abilita gli extra Drive: "
                "`pip install .[drive]` e configura `SERVICE_ACCOUNT_FILE` / `DRIVE_ID`."
            )
        else:
            try:
                with st.status("Genero README nelle sottocartelle di raw/…", expanded=True):
                    # Call “tollerante” a firme diverse
                    try:
                        result = _emit_readmes_for_raw(slug=slug, ensure_structure=False, require_env=True)
                    except TypeError:
                        result = _emit_readmes_for_raw(slug)  # fallback a firma più semplice
                n = len(result or {})
                st.success(f"README creati/aggiornati: {n}")
            except Exception as e:  # pragma: no cover
                st.error(f"Impossibile generare i README: {e}")
