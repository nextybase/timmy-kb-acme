# onboarding_ui.py
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
        st.Page("src/ui/pages/home.py", title="Home"),
        st.Page("src/ui/pages/manage.py", title="Gestisci cliente", url_path="manage"),
        st.Page("src/ui/pages/semantics.py", title="Semantica", url_path="semantics"),
    ],
    "Tools": [
        st.Page("src/ui/pages/preview.py", title="Docker Preview", url_path="preview"),
        st.Page("src/ui/pages/cleanup.py", title="Cleanup", url_path="cleanup"),
    ],
}

navigation = st.navigation(pages, position="top")
navigation.run()


def _diagnostics(slug: str | None) -> None:
    """Expander diagnostico compatibile con i test legacy."""
    import io
    import os
    import zipfile

    from pipeline.context import ClientContext  # type: ignore

    with st.expander("Diagnostica", expanded=False):
        if not slug:
            st.info("Seleziona un cliente per mostrare i dettagli.")
            return

        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            base_dir = ctx.base_dir
        except Exception:
            base_dir = None

        st.write(f"Base dir: `{base_dir or 'n/d'}`")

        def _count(path: Path) -> int:
            total = 0
            for _root, _dirs, files in os.walk(path):
                total += len(files)
            return total

        if base_dir:
            base_path = Path(base_dir)
            raw = base_path / "raw"
            book = base_path / "book"
            semantic = base_path / "semantic"
            st.write(
                f"raw/: **{_count(raw) if raw.is_dir() else 0}** · "
                f"book/: **{_count(book) if book.is_dir() else 0}** · "
                f"semantic/: **{_count(semantic) if semantic.is_dir() else 0}**"
            )

            logs_dir = base_path / "logs"
            if logs_dir.is_dir():
                files = sorted(
                    (p for p in logs_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                latest = files[0] if files else None
                if latest:
                    try:
                        buf = latest.read_bytes()[-4000:]
                        st.code(buf.decode(errors="replace"))
                    except Exception:
                        st.warning("Impossibile leggere il log più recente.")

                    mem = io.BytesIO()
                    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                        for file_path in files:
                            archive.write(file_path, arcname=file_path.name)
                    st.download_button(
                        "Scarica logs",
                        data=mem.getvalue(),
                        file_name=f"{slug}-logs.zip",
                        mime="application/zip",
                    )


def _resolve_slug(slug: str | None) -> str | None:
    """Normalizza lo slug leggendo anche dallo stato sessione."""
    candidates = (
        slug,
        st.session_state.get("ui.manage.selected_slug"),
        st.session_state.get("current_slug"),
        st.session_state.get("slug"),
    )
    for candidate in candidates:
        if candidate is None:
            continue
        trimmed = str(candidate).strip()
        if trimmed:
            return trimmed.lower()
    return None
