# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Callable, Optional, Sequence, cast

from ui.manage._helpers import call_best_effort


def prepare_download_plan(
    plan_fn: Optional[Callable[..., Sequence[Sequence[str]]]],
    *,
    slug: str,
    logger: object,
) -> tuple[list[str], list[str]]:
    if plan_fn is None:
        raise RuntimeError("plan_raw_download non disponibile in ui.services.drive_runner.")
    result = call_best_effort(plan_fn, logger=logger, slug=slug, require_env=True)
    conflicts, labels = cast(tuple[list[str], list[str]], result)
    return conflicts, labels


def render_download_plan(st: object, conflicts: Sequence[str], labels: Sequence[str]) -> None:
    if conflicts:
        with st.expander(f"File già presenti in locale ({len(conflicts)})", expanded=True):
            st.markdown("\n".join(f"- `{x}`" for x in sorted(conflicts)))
    else:
        st.info("Nessun conflitto rilevato: nessun file verrebbe sovrascritto.")

    with st.expander(f"Anteprima destinazioni ({len(labels)})", expanded=False):
        st.markdown("\n".join(f"- `{x}`" for x in sorted(labels)))


def execute_drive_download(
    slug: str,
    conflicts: Sequence[str],
    *,
    download_with_progress: Optional[Callable[..., Sequence[str]]],
    download_simple: Optional[Callable[..., Sequence[str]]],
    invalidate_index: Optional[Callable[[str], None]],
    logger: object,
    st: object,
    status_guard: Callable[..., object],
) -> bool:
    download_fn = download_with_progress or download_simple
    if download_fn is None:
        raise RuntimeError("Funzione di download non disponibile.")

    try:
        with status_guard(
            "Scarico file da Drive...",
            expanded=True,
            error_label="Errore durante il download",
        ) as status_widget:
            try:
                paths = call_best_effort(
                    download_fn,
                    logger=logger,
                    slug=slug,
                    require_env=True,
                    overwrite=bool(conflicts),
                )
            except TypeError:
                paths = call_best_effort(
                    download_fn,
                    logger=logger,
                    slug=slug,
                    overwrite=bool(conflicts),
                )
            count = len(paths or [])
            if status_widget is not None and hasattr(status_widget, "update"):
                status_widget.update(
                    label=f"Download completato. File nuovi/aggiornati: {count}.",
                    state="complete",
                )

        try:
            if invalidate_index is not None:
                invalidate_index(slug)
            st.toast("Allineamento Drive->locale completato.")
            return True
        except Exception:
            return True
    except Exception as exc:
        st.error(f"Errore durante il download: {exc}")
        return False


def render_drive_status_message(st: object, disabled: bool, message: str) -> None:
    if disabled:
        st.info(message)
