# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/diagnostics.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, cast

from pipeline.logging_utils import get_structured_logger
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()
LOGGER = get_structured_logger("ui.diagnostics")

from ui.chrome import render_chrome_then_require
from ui.utils import diagnostics as diag  # verrà monkeypatchato nei test

TAIL_BYTES = 4000


def _warn_once(key: str, event: str, *, slug: str | None, message: str, level: str = "warning") -> None:
    if st.session_state.get(key):
        return
    st.session_state[key] = True
    extra = {"page": "diagnostics", "slug": slug or "", "reason": message, "decision": "HIDE"}
    if level == "error":
        LOGGER.error(event, extra=extra)
        st.error(message)
    else:
        LOGGER.warning(event, extra=extra)
        st.warning(message)


def _render_counts(repo_root_dir: Optional[Path], *, slug: str | None) -> None:
    """Mostra un riepilogo minimale del workspace (raw/normalized/book/semantic)."""
    with st.expander("Workspace", expanded=False):
        if not repo_root_dir:
            st.info("Seleziona un cliente per mostrare i dettagli.")
            return

        try:
            summaries = diag.summarize_workspace_folders(repo_root_dir)
        except Exception as exc:
            _warn_once(
                f"diag_counts_failed_{slug}",
                "ui.diagnostics.counts_failed",
                slug=slug,
                message=f"Impossibile leggere il riepilogo workspace: {exc}",
            )
            return

        if summaries:

            def _fmt(data: tuple[int, bool]) -> str:
                count, truncated = data
                return f">={count}" if truncated else str(count)

            raw = _fmt(summaries.get("raw", (0, False)))
            normalized = _fmt(summaries.get("normalized", (0, False)))
            book = _fmt(summaries.get("book", (0, False)))
            semantic = _fmt(summaries.get("semantic", (0, False)))
            st.write(f"raw/: **{raw}** · normalized/: **{normalized}** · book/: **{book}** · semantic/: **{semantic}**")
        else:
            st.info("Nessun dato disponibile.")


def _render_logs(repo_root_dir: Optional[Path], slug: Optional[str]) -> None:
    """Mostra la coda del log più recente e offre il download dell'archivio."""
    with st.expander("Log", expanded=False):
        if not repo_root_dir:
            st.info("Seleziona un cliente per mostrare i dettagli.")
            return

        # Elenco log
        try:
            log_files = diag.collect_log_files(repo_root_dir)
        except Exception as exc:
            _warn_once(
                f"diag_logs_list_failed_{slug}",
                "ui.diagnostics.logs_list_failed",
                slug=slug,
                message=f"Impossibile elencare i log: {exc}",
            )
            return

        if not log_files:
            st.info("Nessun log trovato.")
            return

        latest = log_files[0]
        reader = diag.get_safe_reader()

        summary = diag.build_workspace_summary(slug or "unknown", log_files, repo_root_dir=repo_root_dir)
        if summary:
            st.caption("Workspace summary")
            st.json(summary)

        # Tail del log (<= TAIL_BYTES)
        try:
            tail_bytes = diag.tail_log_bytes(latest, safe_reader=reader, tail_bytes=TAIL_BYTES)
            if tail_bytes:
                try:
                    st.code(tail_bytes.decode(errors="replace"))
                except Exception:
                    st.code(tail_bytes)
        except Exception as exc:
            _warn_once(
                f"diag_logs_tail_failed_{slug}",
                "ui.diagnostics.logs_tail_failed",
                slug=slug,
                message=f"Impossibile leggere il log più recente: {exc}",
            )

        # Download archivio log
        try:
            archive = diag.build_logs_archive(log_files, slug=slug or "unknown", safe_reader=reader)
            if archive:
                st.download_button(
                    "Scarica logs",
                    data=archive,
                    file_name=f"{(slug or 'logs')}.zip",
                    mime="application/zip",
                )
        except Exception as exc:
            _warn_once(
                f"diag_logs_archive_failed_{slug}",
                "ui.diagnostics.logs_archive_failed",
                slug=slug,
                message=f"Archivio log non disponibile: {exc}",
            )


def main() -> None:
    """Pagina Diagnostica: header, sidebar, counts e log tail."""
    slug = cast(str, render_chrome_then_require())

    st.subheader("Diagnostica")

    try:
        repo_root_dir = diag.resolve_repo_root_dir(slug)
    except Exception as exc:
        LOGGER.error(
            "ui.diagnostics.repo_root_dir_failed",
            extra={"page": "diagnostics", "slug": slug or "", "reason": str(exc), "decision": "STOP"},
        )
        st.error(f"Impossibile risolvere la repo root: {exc}")
        st.stop()

    st.write(f"Repo root: `{repo_root_dir}`")

    _render_counts(repo_root_dir, slug=slug)
    _render_logs(repo_root_dir, slug)


# Esportiamo esplicitamente i simboli usati nei test
__all__ = ["_render_logs", "_render_counts", "main"]

if __name__ == "__main__":
    main()
