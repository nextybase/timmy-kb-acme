# onboarding_ui.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Onboarding UI entrypoint.

- Reuse existing repo helper to add <repo>/src to sys.path (scripts/smoke_e2e._add_paths),
  con fallback locale se non disponibile.
- Configurazione pagina Streamlit come prima istruzione UI.
- Wrapper che lascia passare RerunException (usato da st.rerun) e mostra gli altri errori
  in un expander "Dettagli tecnici".
- Nessuna modifica alla business-logic: delega a src.ui.app.main()
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException


# ------------------------------------------------------------------------------
# Path bootstrap: prova ad usare l'helper del repo, con fallback locale
# ------------------------------------------------------------------------------

def _ensure_repo_src_on_sys_path() -> None:
    """Aggiunge <repo>/src a sys.path se assente (fallback)."""
    repo_root = Path(__file__).parent.resolve()
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _bootstrap_sys_path() -> None:
    """Tenta l'helper ufficiale del repo, poi fallback locale."""
    try:
        # Helper già presente nel repo di test/smoke
        from scripts.smoke_e2e import _add_paths as _repo_add_paths  # type: ignore

        _repo_add_paths()
    except Exception:
        # Fallback robusto
        _ensure_repo_src_on_sys_path()


# Esegui bootstrap path il prima possibile
_bootstrap_sys_path()


# ------------------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------------------

def _page_config() -> None:
    # Deve essere la PRIMA chiamata Streamlit della pagina
    st.set_page_config(page_title="Onboarding NeXT - Clienti", layout="wide")


def _render_global_error(e: Exception) -> None:
    st.error("Si è verificato un errore non gestito nell'interfaccia.")
    with st.expander("Dettagli tecnici", expanded=False):
        st.exception(e)


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------

def run() -> None:
    _page_config()

    # Import ritardato: evita errori prima della config della pagina
    try:
        from src.ui.app import main as app_main  # type: ignore
    except Exception as e:  # noqa: BLE001
        _render_global_error(e)
        return

    try:
        app_main()  # nessuna modifica alla business logic
    except RerunException:
        # NON è un errore: Streamlit usa questa eccezione per gestire st.rerun()
        raise
    except Exception as e:  # noqa: BLE001
        _render_global_error(e)


if __name__ == "__main__":
    run()
