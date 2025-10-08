# SPDX-License-Identifier: GPL-3.0-or-later
"""
Onboarding UI entrypoint (beta 0, navigazione nativa).
- Router nativo Streamlit (st.navigation + st.Page).
- Deep-linking via st.query_params.
- Path bootstrap per garantire import di src/.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_src_on_sys_path() -> None:
    """Aggiunge <repo>/src a sys.path se assente."""
    repo_root = Path(__file__).parent.resolve()
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _bootstrap_sys_path() -> None:
    """Prova l'helper ufficiale, altrimenti fallback locale."""
    try:
        from scripts.smoke_e2e import _add_paths as _repo_add_paths  # type: ignore
    except Exception:
        _ensure_repo_src_on_sys_path()
        return
    try:
        _repo_add_paths()
    except Exception:
        _ensure_repo_src_on_sys_path()


_bootstrap_sys_path()

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Timmy-KB - Onboarding",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _hydrate_query_defaults() -> None:
    query = st.query_params.to_dict()
    if "tab" not in query:
        st.query_params["tab"] = "home"


_hydrate_query_defaults()

pages = {
    "Onboarding": [
        # Home come pagina di default (niente url_path vuoto)
        st.Page("src/ui/pages/home.py", title="Home", default=True),
        st.Page("src/ui/pages/manage.py", title="Gestisci cliente", url_path="manage"),
        st.Page("src/ui/pages/semantics.py", title="Semantica", url_path="semantics"),
    ],
    "Tools": [
        st.Page("src/ui/pages/preview.py", title="Docker Preview", url_path="preview"),
        st.Page("src/ui/pages/cleanup.py", title="Cleanup", url_path="cleanup"),
        st.Page("src/ui/pages/diagnostics.py", title="Diagnostica", url_path="diagnostics"),
    ],
}

navigation = st.navigation(pages, position="top")
navigation.run()
