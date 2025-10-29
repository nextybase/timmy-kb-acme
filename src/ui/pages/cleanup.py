# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/cleanup.py
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any, Callable, Optional, cast

from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import render_chrome_then_require
from ui.clients_store import load_clients as _load_clients
from ui.utils import resolve_raw_dir, set_slug
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401


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
_run_cleanup = (
    _safe_get("timmykb.tools.clean_client_workspace:run_cleanup")
    or _safe_get("tools.clean_client_workspace:run_cleanup")
    or _safe_get("src.tools.clean_client_workspace:run_cleanup")
)
_perform_cleanup = (
    _safe_get("timmykb.tools.clean_client_workspace:perform_cleanup")
    or _safe_get("tools.clean_client_workspace:perform_cleanup")
    or _safe_get("src.tools.clean_client_workspace:perform_cleanup")
)


def _load_run_cleanup() -> Optional[Callable[..., Any]]:
    """Tenta di ricaricare `run_cleanup` dai namespace supportati."""
    return (
        _safe_get("timmykb.tools.clean_client_workspace:run_cleanup")
        or _safe_get("tools.clean_client_workspace:run_cleanup")
        or _safe_get("src.tools.clean_client_workspace:run_cleanup")
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
        set_tab("home")
    except Exception:
        pass
    st.rerun()


# ---- UI chrome ----
slug = render_chrome_then_require(allow_without_slug=True)
if not slug:
    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()

slug = cast(str, slug)

st.subheader("Cleanup")
st.write("Strumenti di pulizia del workspace e **cancellazione definitiva** del cliente.")

# --- Esito ultima operazione (mostrato nel main dopo la chiusura del modal) ---
_last = st.session_state.pop("__cleanup_done", None)
if isinstance(_last, dict) and _last.get("text"):
    level = (_last.get("level") or "success").strip().lower()
    if level == "warning":
        st.warning(_last["text"])
    elif level == "error":
        st.error(_last["text"])
    else:
        st.success(_last["text"])

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


def _open_confirm_dialog() -> None:
    """Apre il modal di conferma e gestisce l'esecuzione del cleanup."""
    target = slug

    def _modal() -> None:
        st.warning(
            f"⚠️ Eliminazione **IRREVERSIBILE** del cliente **{client_name}** (`{target}`)\n\n"
            "**Verrà rimosso:**\n"
            f"- Cartella locale `output/timmy-kb-{target}` (incluse cartelle in `raw/`)\n"
            "- Record in `clients_db/clients.yaml`\n"
            f"- Cartella cliente su Drive (radice: `{target}`)\n\n"
            "Confermi?",
            icon="⚠️",
        )

        c1, c2 = st.columns(2)
        if c1.button("Annulla", key="cleanup_cancel", type="secondary", width="stretch"):
            return

        if c2.button("Conferma eliminazione", key="cleanup_do_delete", type="primary", width="stretch"):
            code: Optional[int] = None
            messages: list[tuple[str, str]] = []
            runner_error = None

            # 1) Percorso 'ricco' (ritorna dettagli per sezione)
            if callable(_perform_cleanup):
                try:
                    results = _perform_cleanup(target, client_name=client_name)
                    code = int(results.get("exit_code", 1))
                    for section in ("drive", "local", "registry"):
                        info = results.get(section) or {}
                        msg = info.get("message")
                        if msg:
                            messages.append((section.upper(), msg))
                except Exception as exc:
                    runner_error = exc
            else:
                # 2) Fallback alla funzione CLI con cattura output
                runner_candidate = _run_cleanup or _load_run_cleanup()
                callable_runner = runner_candidate if callable(runner_candidate) else None
                if callable_runner is None:
                    st.session_state["__cleanup_done"] = {
                        "level": "error",
                        "text": "Funzione di cancellazione non disponibile. "
                        "Verifica che `tools.clean_client_workspace` sia importabile (con o senza prefisso `src`).",
                    }
                    st.rerun()
                    return
                buffer = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                        code = int(callable_runner(target, True))  # assume_yes=True
                except Exception as exc:
                    runner_error = exc
                captured = buffer.getvalue().strip()
                if captured:
                    messages.append(("LOG", captured))

            if runner_error is not None:
                st.session_state["__cleanup_done"] = {
                    "level": "error",
                    "text": f"Errore durante la cancellazione: {runner_error}",
                }
                st.rerun()

            if code is None:
                st.session_state["__cleanup_done"] = {
                    "level": "error",
                    "text": "Risultato della cancellazione non disponibile.",
                }
                st.rerun()

            # Reporter sintetico nel main dopo la chiusura del modal
            # e reset dello slug attivo.
            if code == 0:
                set_slug("")
                st.session_state["__cleanup_done"] = {
                    "level": "success",
                    "text": f"Cliente '{client_name}' eliminato correttamente.",
                }
            elif code == 3:
                set_slug("")
                st.session_state["__cleanup_done"] = {
                    "level": "warning",
                    "text": "Workspace locale e DB rimossi. Cartella Drive non eliminata per permessi/driver.",
                }
            elif code == 4:
                st.session_state["__cleanup_done"] = {
                    "level": "error",
                    "text": "Rimozione locale incompleta: verifica file bloccati e riprova.",
                }
            else:
                st.session_state["__cleanup_done"] = {
                    "level": "error",
                    "text": "Operazione completata con avvisi o errori parziali.",
                }
            st.rerun()  # chiude il modal e mostra l'esito nel main

    dialog_builder = getattr(st, "dialog", None)
    if callable(dialog_builder):
        dialog_fn = cast(Callable[..., Callable[[Callable[[], None]], Any]], dialog_builder)
        decorator = dialog_fn("Conferma eliminazione cliente", width="large")
        if callable(decorator):
            maybe_runner = decorator(_modal)
            if callable(maybe_runner):
                maybe_runner()
            else:
                _modal()
        else:
            _modal()
    else:
        _modal()


if st.button(
    "Cancella cliente…",
    key="cleanup_open_confirm",
    type="secondary",
    help="Rimozione completa: locale, DB e Drive",
    width="stretch",
):
    _open_confirm_dialog()
