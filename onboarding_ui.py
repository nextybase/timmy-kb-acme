from __future__ import annotations

import traceback

import streamlit as st

# Delega alla UI principale senza toccare la business logic
from src.ui.app import main as app_main


def _page_config() -> None:
    # UI-only: miglior disponibilità spazio e titolo chiaro
    st.set_page_config(
        page_title="Onboarding NeXT — UI",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def _render_global_errors(err: BaseException) -> None:
    # Messaggi brevi in UI, dettaglio facoltativo
    st.error("Si è verificato un errore non gestito nell'interfaccia.")
    with st.expander("Dettagli tecnici", expanded=False):
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        st.code(tb, language="python")


def run() -> None:
    _page_config()
    try:
        app_main()  # nessuna modifica alla logica applicativa
    except SystemExit as se:  # consente chiusure intenzionali
        raise se
    except BaseException as err:  # pragma: no cover
        _render_global_errors(err)


if __name__ == "__main__":
    run()
