# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import header, sidebar
from ui.utils import get_slug, set_slug


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione se disponibile, altrimenti None. Formato: 'pkg.mod:func'."""
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Services UI
_render_drive_tree = _safe_get("ui.services.drive:render_drive_tree")
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")

# Tool di pulizia workspace (locale + DB + Drive)
# run_cleanup(slug: str, assume_yes: bool = False) -> int
_run_cleanup = _safe_get("src.tools.clean_client_workspace:run_cleanup")


def _reset_manage_delete_state() -> None:
    """Ripulisce lo stato dopo la cancellazione drive/local/DB."""
    set_slug("")
    st.session_state.pop("__confirm_delete_open", None)
    st.session_state.pop("__confirm_delete_slug", None)
    st.session_state.pop("manage_slug", None)


# ---------------- UI ----------------

slug = get_slug()
set_slug(slug)

header(slug)
sidebar(slug)

_feedback = st.session_state.pop("manage_cleanup_feedback", None)
if _feedback:
    level, message = _feedback
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    else:
        st.info(message)

# Stato: se lo slug non è settato mostriamo il blocco "Gestione cliente" (input + azioni)
if not slug:
    st.subheader("Gestione cliente")

    entered_slug = st.text_input(
        "Slug cliente",
        value="",
        placeholder="es. acme",
        key="manage_slug",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Apri workspace", key="manage_open_workspace", width="stretch"):
            set_slug((entered_slug or "").strip())
            st.rerun()

    with col_b:
        # Avvio procedura di cancellazione con conferma esplicita
        if st.button("Cancella cliente", key="manage_delete_client", width="stretch"):
            target = (entered_slug or "").strip()
            if not target:
                st.warning("Inserisci uno slug valido prima di cancellare.")
            else:
                st.session_state["__confirm_delete_slug"] = target
                st.session_state["__confirm_delete_open"] = True
                st.rerun()

    # Dialog di conferma (semplice, gestito a stato)
    if st.session_state.get("__confirm_delete_open"):
        target = st.session_state.get("__confirm_delete_slug", "")
        with st.container(border=True):
            st.warning(
                f"⚠️ Eliminazione IRREVERSIBILE del workspace **{target}**:\n"
                "- Cartella locale `output/timmy-kb-<slug>`\n"
                "- Record in `clients_db/clients.yaml`\n"
                "- Cartella cliente su Drive (se presente)\n"
                "Confermi?",
                icon="⚠️",
            )
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Annulla", key="cancel_delete"):
                    st.session_state.pop("__confirm_delete_open", None)
                    st.session_state.pop("__confirm_delete_slug", None)
                    st.rerun()
            with c2:
                if st.button("Conferma eliminazione", key="do_delete"):
                    feedback_payload: tuple[str, str] | None = None
                    if callable(_run_cleanup):
                        # Esegue in modalità non interattiva con conferma forzata
                        code = int(_run_cleanup(target, True))  # assume_yes=True  :contentReference[oaicite:2]{index=2}
                        if code == 0:
                            feedback_payload = ("success", f"Cliente '{target}' eliminato correttamente.")
                        elif code == 3:
                            feedback_payload = (
                                "warning",
                                (
                                    "Workspace locale e DB rimossi."
                                    " Cartella Drive non eliminata per permessi insufficienti."
                                ),
                            )
                        elif code == 4:
                            st.error("Rimozione locale incompleta: verifica file bloccati e riprova.")
                        else:
                            st.error("Operazione completata con avvisi o errori parziali.")
                    else:
                        st.error(
                            "Funzione di cancellazione non disponibile. Verifica che il modulo "
                            "`src.tools.clean_client_workspace` sia importabile."
                        )
                    if feedback_payload is not None:
                        st.session_state["manage_cleanup_feedback"] = feedback_payload
                        _reset_manage_delete_state()
                        st.rerun()
                    else:
                        st.session_state.pop("__confirm_delete_open", None)
                        st.session_state.pop("__confirm_delete_slug", None)

    st.info("Inserisci uno slug e premi **Apri workspace** oppure **Cancella cliente**.")
    st.stop()

# Da qui in poi: slug presente → mostriamo direttamente le viste operative
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
