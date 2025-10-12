# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/cleanup.py
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any, Callable, Optional

import streamlit as st

from ui.chrome import render_chrome_then_require
from ui.clients_store import load_clients as _load_clients
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
# Prova entrambe le forme del modulo, a seconda del run-path.
_run_cleanup = _safe_get("tools.clean_client_workspace:run_cleanup") or _safe_get(
    "src.tools.clean_client_workspace:run_cleanup"
)
_perform_cleanup = _safe_get("tools.clean_client_workspace:perform_cleanup") or _safe_get(
    "src.tools.clean_client_workspace:perform_cleanup"
)


def _load_run_cleanup() -> Optional[Callable[..., Any]]:
    """Tenta di ricaricare `run_cleanup` dai namespace supportati."""
    return _safe_get("tools.clean_client_workspace:run_cleanup") or _safe_get(
        "src.tools.clean_client_workspace:run_cleanup"
    )


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
                code: Optional[int] = None
                messages: list[tuple[str, str]] = []
                runner_error = None

                if callable(_perform_cleanup):
                    try:
                        results = _perform_cleanup(target, client_name=client_name)
                        code = int(results.get("exit_code", 1))
                        for section in ("drive", "local", "registry"):
                            info = results.get(section) or {}
                            message = info.get("message")
                            if message:
                                messages.append((section.upper(), message))
                    except Exception as exc:
                        runner_error = exc
                else:
                    runner = _run_cleanup or _load_run_cleanup()
                    if not callable(runner):
                        st.error(
                            "Funzione di cancellazione non disponibile. "
                            "Verifica che `tools.clean_client_workspace` sia importabile (con o senza prefisso `src`)."
                        )
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                        runner_error = RuntimeError("Funzione run_cleanup non disponibile")
                    else:
                        buffer = io.StringIO()
                        try:
                            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                                code = int(runner(target, True))  # assume_yes=True
                        except Exception as exc:
                            runner_error = exc
                        captured = buffer.getvalue().strip()
                        if captured:
                            messages.append(("LOG", captured))

                if runner_error is not None:
                    st.error(f"Errore durante la cancellazione: {runner_error}")
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
                elif code is None:
                    st.error("Risultato della cancellazione non disponibile.")
                    st.session_state.pop("__cleanup_confirm_open", None)
                    st.session_state.pop("__cleanup_confirm_slug", None)
                else:
                    with st.status(f"Elimino il cliente **{client_name}**…", expanded=True) as status:
                        for label, message in messages:
                            status.write(f"[{label}] {message}")

                    if code == 0:
                        st.success(f"Cliente '{client_name}' eliminato correttamente.")
                        set_slug("")
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                        _redirect_home()
                    elif code == 3:
                        st.warning("Workspace locale e DB rimossi. Cartella Drive non eliminata per permessi/driver.")
                        set_slug("")
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                        _redirect_home()
                    elif code == 4:
                        st.error("Rimozione locale incompleta: verifica file bloccati e riprova.")
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
                    else:
                        st.error("Operazione completata con avvisi o errori parziali.")
                        st.session_state.pop("__cleanup_confirm_open", None)
                        st.session_state.pop("__cleanup_confirm_slug", None)
