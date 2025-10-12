# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/cleanup.py
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import render_chrome_then_require
from ui.clients_store import load_clients as _load_clients
from ui.utils import resolve_raw_dir, set_slug


def _repo_root() -> Path:
    # cleanup.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _load_run_cleanup() -> Optional[Callable[..., Any]]:
    """
    Trova `run_cleanup` provando namespace multipli e, in fallback, il file locale.
    """
    candidates = [
        ("src.tools.clean_client_workspace", "run_cleanup"),
        ("tools.clean_client_workspace", "run_cleanup"),
    ]
    for module_name, func_name in candidates:
        try:
            module = importlib.import_module(module_name)
            func = getattr(module, func_name, None)
            if callable(func):
                return func
        except Exception:
            continue

    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    file_path = repo / "src" / "tools" / "clean_client_workspace.py"
    if file_path.exists():
        spec = importlib.util.spec_from_file_location("_cleanup_cli", file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                func = getattr(module, "run_cleanup", None)
                if callable(func):
                    return func
            except Exception:
                pass
    return None


# Orchestratore di cancellazione (locale + DB + Drive)
# run_cleanup(slug: str, assume_yes: bool = False) -> int
_run_cleanup = _load_run_cleanup()


def _client_display_name(slug: str) -> str:
    """Recupera il nome cliente dal registry SSoT; fallback allo slug."""
    try:
        for entry in _load_clients():
            if entry.slug.strip().lower() == slug.strip().lower():
                name = (entry.nome or "").strip()
                return name or entry.slug
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
                current = _run_cleanup
                if not callable(current):
                    current = _load_run_cleanup()
                if not callable(current):
                    st.error(
                        "Funzione di cancellazione non disponibile. "
                        "Verifica che `tools.clean_client_workspace` sia importabile (con o senza prefisso `src`)."
                    )
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
                else:
                    with st.status(f"Elimino il cliente **{client_name}**…", expanded=True):
                        code = int(current(target, True))  # assume_yes=True
                    if code == 0:
                        st.success(f"Cliente '{client_name}' eliminato correttamente.")
                        set_slug("")  # rimuove lo slug attivo (query + session + persistenza)
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                        _redirect_home()  # torna alla home completa
                    elif code == 3:
                        st.warning("Workspace locale e DB rimossi. Cartella Drive non eliminata per permessi/driver.")
                        set_slug("")  # pulisco selezione corrente
                        _redirect_home()
                    elif code == 4:
                        st.error("Rimozione locale incompleta: verifica file bloccati e riprova.")
                    else:
                        st.error("Operazione completata con avvisi o errori parziali.")
                    # chiude il dialogo se non abbiamo fatto redirect/rerun
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
