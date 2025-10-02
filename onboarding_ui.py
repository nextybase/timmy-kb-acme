from __future__ import annotations

# --- Bootstrap path: riuso funzione esistente; fallback minimo se non disponibile ---
try:
    from scripts.smoke_e2e import _add_paths as _add_repo_paths  # inserisce ROOT e SRC in sys.path
    _add_repo_paths()
except Exception:
    import sys
    from pathlib import Path

    SRC_DIR = Path(__file__).resolve().parent / "src"
    src_str = str(SRC_DIR)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

import traceback
import streamlit as st

# Import UI principale (gestisce lui set_page_config)
from src.ui.app import main as app_main  # noqa: E402


def _render_global_errors(err: BaseException) -> None:
    st.error("Si è verificato un errore non gestito nell'interfaccia.")
    with st.expander("Dettagli tecnici", expanded=False):
        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        st.code(tb, language="python")


def run() -> None:
    try:
        app_main()  # nessuna modifica alla business logic
    except SystemExit as se:
        raise se
    except BaseException as err:  # pragma: no cover
        _render_global_errors(err)


if __name__ == "__main__":
    run()
