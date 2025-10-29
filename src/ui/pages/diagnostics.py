# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/diagnostics.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, cast

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import render_chrome_then_require
from ui.utils import diagnostics as diag  # verrà monkeypatchato nei test

TAIL_BYTES = 4000


def _render_counts(base_dir: Optional[Path]) -> None:
    """Mostra un riepilogo minimale del workspace (raw/book/semantic)."""
    with st.expander("Workspace", expanded=False):
        if not base_dir:
            st.info("Seleziona un cliente per mostrare i dettagli.")
            return

        try:
            summaries = diag.summarize_workspace_folders(base_dir)
        except Exception:
            summaries = {}

        if summaries:

            def _fmt(data: tuple[int, bool]) -> str:
                count, truncated = data
                return f">={count}" if truncated else str(count)

            raw = _fmt(summaries.get("raw", (0, False)))
            book = _fmt(summaries.get("book", (0, False)))
            semantic = _fmt(summaries.get("semantic", (0, False)))
            st.write(f"raw/: **{raw}** · book/: **{book}** · semantic/: **{semantic}**")
        else:
            st.info("Nessun dato disponibile.")


def _render_logs(base_dir: Optional[Path], slug: Optional[str]) -> None:
    """Mostra la coda del log più recente e offre il download dell’archivio."""
    with st.expander("Log", expanded=False):
        if not base_dir:
            st.info("Seleziona un cliente per mostrare i dettagli.")
            return

        # Elenco log
        try:
            log_files = diag.collect_log_files(base_dir)
        except Exception:
            log_files = []

        if not log_files:
            st.info("Nessun log trovato.")
            return

        latest = log_files[0]

        # Tail del log (<= TAIL_BYTES)
        try:
            tail_bytes = diag.tail_log_bytes(latest, safe_reader=diag.get_safe_reader(), tail_bytes=TAIL_BYTES)
            if tail_bytes:
                try:
                    st.code(tail_bytes.decode(errors="replace"))
                except Exception:
                    st.code(tail_bytes)
        except Exception:
            st.warning("Impossibile leggere il log più recente.")

        # Download archivio log
        try:
            archive = diag.build_logs_archive(log_files, slug=slug or "unknown", safe_reader=diag.get_safe_reader())
            if archive:
                st.download_button(
                    "Scarica logs",
                    data=archive,
                    file_name=f"{(slug or 'logs')}.zip",
                    mime="application/zip",
                    width="stretch",
                )
        except Exception:
            # best-effort: la pagina resta utilizzabile anche senza archivio
            pass


def main() -> None:
    """Pagina Diagnostica: header, sidebar, counts e log tail."""
    slug = cast(str, render_chrome_then_require())

    st.subheader("Diagnostica")

    try:
        base_dir = diag.resolve_base_dir(slug)
    except Exception:
        base_dir = None

    st.write(f"Base dir: `{base_dir or 'n/d'}`")

    _render_counts(base_dir)
    _render_logs(base_dir, slug)


# Esportiamo esplicitamente i simboli usati nei test
__all__ = ["_render_logs", "_render_counts", "main"]

if __name__ == "__main__":
    main()
