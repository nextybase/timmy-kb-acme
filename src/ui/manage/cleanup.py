# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, cast

from pipeline.workspace_layout import WorkspaceLayout
from ui.manage import _helpers as manage_helpers

_RUN_CLEANUP_PATHS: Sequence[str] = (
    "tools.clean_client_workspace:run_cleanup",
    "src.tools.clean_client_workspace:run_cleanup",
)

_PERFORM_CLEANUP_PATHS: Sequence[str] = (
    "tools.clean_client_workspace:perform_cleanup",
    "src.tools.clean_client_workspace:perform_cleanup",
)


def _first_available(paths: Sequence[str]) -> Optional[Callable[..., Any]]:
    for path in paths:
        candidate = manage_helpers.safe_get(path)
        if callable(candidate):
            return cast(Callable[..., Any], candidate)
    return None


def resolve_run_cleanup() -> Optional[Callable[..., Any]]:
    """Ritorna il primo `run_cleanup` disponibile tra i namespace supportati."""
    return _first_available(_RUN_CLEANUP_PATHS)


def resolve_perform_cleanup() -> Optional[Callable[..., Any]]:
    """Ritorna `perform_cleanup` se disponibile (dettagli per Drive/locale/registry)."""
    return _first_available(_PERFORM_CLEANUP_PATHS)


def client_display_name(slug: str, load_clients: Callable[[], Iterable[Any]]) -> str:
    """Restituisce il nome cliente leggendo il registry; fallback allo slug."""
    try:
        for entry in load_clients():
            entry_slug = getattr(entry, "slug", "") or ""
            if entry_slug.strip().lower() == slug.strip().lower():
                display = getattr(entry, "nome", "") or ""
                return (display or entry_slug).strip() or slug
    except Exception:
        pass
    return slug


def list_raw_subfolders(
    slug: str,
    resolve_raw_dir: Callable[[str], Path],
    layout: WorkspaceLayout | None = None,
) -> list[str]:
    """Ritorna le sottocartelle presenti dentro raw/ per il cliente indicato."""
    try:
        raw_dir = layout.raw_dir if layout is not None else Path(resolve_raw_dir(slug))
        if not raw_dir.exists():
            return []
        return sorted(child.name for child in raw_dir.iterdir() if child.is_dir())
    except Exception:
        return []


def open_cleanup_modal(
    *,
    st: Any,
    slug: str,
    client_name: str,
    set_slug: Callable[[str], None],
    run_cleanup: Optional[Callable[..., Any]],
    perform_cleanup: Optional[Callable[..., Any]],
    session_key: str = "__cleanup_done",
) -> None:
    """Mostra il modal di conferma e orchestra l'esecuzione del cleanup."""
    runner = run_cleanup

    def _ensure_runner() -> Optional[Callable[..., Any]]:
        nonlocal runner
        if runner is None:
            runner = resolve_run_cleanup()
        return runner

    def _store(level: str, text: str, *, clear_slug: bool = False) -> None:
        st.session_state[session_key] = {"level": level, "text": text}
        if clear_slug:
            try:
                set_slug("")
            except Exception:
                pass
        st.rerun()

    def _modal() -> None:
        st.warning(
            f"⚠️ Eliminazione **IRREVERSIBILE** del cliente **{client_name}** (`{slug}`)\n\n"
            "**Verrà rimosso:**\n"
            f"- Cartella locale `output/timmy-kb-{slug}` (incluse cartelle in `raw/`)\n"
            "- Record in `clients_db/clients.yaml`\n"
            f"- Cartella cliente su Drive (radice: `{slug}`)\n\n"
            "Confermi?",
            icon="⚠️",
        )

        c1, c2 = st.columns(2)
        if c1.button("Annulla", key="cleanup_cancel", type="secondary", width="stretch"):
            return

        if c2.button("Conferma eliminazione", key="cleanup_do_delete", type="primary", width="stretch"):
            code: Optional[int] = None
            runner_error: Optional[BaseException] = None

            if callable(perform_cleanup):
                try:
                    results = perform_cleanup(slug, client_name=client_name)
                    code = int(results.get("exit_code", 1)) if isinstance(results, dict) else 1
                except Exception as exc:  # pragma: no cover - logging gestito a monte
                    runner_error = exc
            else:
                callable_runner = _ensure_runner()
                if callable_runner is None:
                    _store(
                        "error",
                        "Funzione di cancellazione non disponibile. "
                        "Verifica che `tools.clean_client_workspace` sia importabile (con o senza prefisso `src`).",
                    )
                    return
                buffer = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                        code = int(callable_runner(slug, True))  # assume_yes=True
                except Exception as exc:  # pragma: no cover - logging gestito a monte
                    runner_error = exc

            if runner_error is not None:
                _store("error", f"Errore durante la cancellazione: {runner_error}")
                return

            if code is None:
                _store("error", "Risultato della cancellazione non disponibile.")
                return

            if code == 0:
                _store("success", f"Cliente '{client_name}' eliminato correttamente.", clear_slug=True)
            elif code == 3:
                _store(
                    "warning",
                    "Workspace locale e DB rimossi. Cartella Drive non eliminata per permessi/driver.",
                    clear_slug=True,
                )
            elif code == 4:
                _store("error", "Rimozione locale incompleta: verifica file bloccati e riprova.")
            else:
                _store("error", "Operazione completata con avvisi o errori parziali.")

    decorator = st.dialog("Conferma eliminazione cliente", width="large")
    runner_candidate = decorator(_modal)
    if callable(runner_candidate):
        runner_candidate()
    else:
        _modal()
