# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/cleanup.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import streamlit as st

from pipeline.yaml_utils import yaml_read
from ui.chrome import render_chrome_then_require
from ui.utils import resolve_raw_dir, set_slug


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione se disponibile, altrimenti None. Formato: 'pkg.mod:func'."""
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Orchestratore di cancellazione (locale + DB + Drive)
# run_cleanup(slug: str, assume_yes: bool = False) -> int
_run_cleanup = _safe_get("src.tools.clean_client_workspace:run_cleanup")


# ---- Helpers ----
def _repo_root() -> Path:
    # cleanup.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _clients_db_path() -> Path:
    return _repo_root() / "clients_db" / "clients.yaml"


def _client_display_name(slug: str) -> str:
    """Legge il nome cliente dal DB; fallback allo slug."""
    try:
        dbp = _clients_db_path()
        if dbp.exists():
            data = yaml_read(dbp.parent, dbp)
            records = data if isinstance(data, list) else []
            for rec in records:
                if (rec or {}).get("slug", "").strip().lower() == slug.strip().lower():
                    name = (rec or {}).get("nome", "") or ""
                    return name.strip() or slug
    except Exception:
        pass
    return slug


def _list_raw_subfolders(slug: str) -> list[str]:
    """Ritorna le sottocartelle immediate dentro RAW/."""
    try:
        raw_dir = Path(resolve_raw_dir(slug))
        if not raw_dir.exists():
            return []
        return sorted([p.name for p in raw_dir.iterdir() if p.is_dir()])
    except Exception:
        return []


def _redirect_home() -> None:
    """Redirect immediato alla home nella stessa scheda."""
    try:
        st.query_params["tab"] = "home"
    except Exception:
        pass
    st.rerun()


# ---- UI chrome ----
slug = render_chrome_then_require(allow_without_slug=True)
if not slug:
    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()

st.subheader("Cleanup")
st.write("Strumenti di pulizia del workspace e **cancellazione definitiva** del cliente.")

# --- Riepilogo di ciò che verrà cancellato ---
st.markdown("---")
st.markdown("### Cosa verrà cancellato")

client_name = _client_display_name(slug)
raw_folders = _list_raw_subfolders(slug)

st.markdown(f"**Cliente:** {client_name}  \n" f"**Google Drive:** `{slug}`")

if raw_folders:
    raw_list = ", ".join(f"`{name}`" for name in raw_folders)
    st.markdown(f"**Cartelle RAW:** {raw_list}")
else:
    st.markdown("**Cartelle RAW:** *(nessuna cartella trovata o RAW non presente)*")

# --- Danger zone: cancellazione cliente ---
st.markdown("---")
st.markdown("### Danger zone")

if st.button(
    "Cancella cliente…",
    key="cleanup_open_confirm",
    type="secondary",
    help="Rimozione completa: locale, DB e Drive",
):
    st.session_state["__cleanup_confirm_open"] = True
    st.session_state["__cleanup_confirm_slug"] = slug
    st.rerun()

if st.session_state.get("__cleanup_confirm_open"):
    target = st.session_state.get("__cleanup_confirm_slug", slug or "")
    with st.container(border=True):
        st.warning(
            f"⚠️ Eliminazione **IRREVERSIBILE** del cliente **{client_name}** (`{target}`)\n\n"
            "**Verrà rimosso:**\n"
            "- Cartella locale `output/timmy-kb-{target}` (incluse cartelle in `raw/`)\n"
            "- Record in `clients_db/clients.yaml`\n"
            "- Cartella cliente su Drive (radice: `{target}`)\n\n"
            "Confermi?",
            icon="⚠️",
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Annulla", key="cleanup_cancel"):
                st.session_state.pop("__cleanup_confirm_open", None)
                st.session_state.pop("__cleanup_confirm_slug", None)
                st.rerun()
        with c2:
            if st.button("Conferma eliminazione", key="cleanup_do_delete"):
                if not callable(_run_cleanup):
                    st.error(
                        "Funzione di cancellazione non disponibile. "
                        "Verifica che `src.tools.clean_client_workspace` sia importabile."
                    )
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
                else:
                    with st.status(f"Elimino il cliente **{client_name}**…", expanded=True):
                        code = int(_run_cleanup(target, True))  # assume_yes=True
                    if code == 0:
                        st.success(f"Cliente '{client_name}' eliminato correttamente.")
                        set_slug("")  # rimuove lo slug attivo (query + session + persistenza)
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                        _redirect_home()  # torna alla home completa
                    elif code == 3:
                        st.warning(
                            "Workspace locale e DB rimossi. " "Cartella Drive non eliminata per permessi insufficienti."
                        )
                    elif code == 4:
                        st.error("Rimozione locale incompleta: verifica file bloccati e riprova.")
                    else:
                        st.error("Operazione completata con avvisi o errori parziali.")
                    # chiude il dialogo se non abbiamo fatto redirect/rerun
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
