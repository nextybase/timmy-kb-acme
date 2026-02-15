# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable, ContextManager, Optional, Protocol, Sequence, cast

from pipeline.exceptions import PipelineError
from ui.manage._helpers import call_strict
from ui.types import StreamlitLike


class StatusGuard(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> ContextManager[Any]: ...


def prepare_download_plan(
    plan_fn: Optional[Callable[..., Sequence[Sequence[str]]]],
    *,
    slug: str,
    logger: Any,
) -> tuple[list[str], list[str]]:
    if plan_fn is None:
        raise RuntimeError("plan_raw_download non disponibile in ui.services.drive_runner.")
    result = cast(Sequence[Sequence[str]], call_strict(plan_fn, logger=logger, slug=slug, require_env=True))
    try:
        conflicts_raw, labels_raw = tuple(result)
    except (TypeError, ValueError):
        raise RuntimeError("plan_raw_download deve restituire (conflicts, labels)") from None
    conflicts = list(conflicts_raw)
    labels = list(labels_raw)
    return conflicts, labels


def render_download_plan(st: StreamlitLike, conflicts: Sequence[str], labels: Sequence[str]) -> None:
    if conflicts:
        with st.expander(f"File già presenti in locale ({len(conflicts)})", expanded=True):
            st.markdown("\n".join(f"- `{x}`" for x in sorted(conflicts)))
    else:
        st.info("Nessun conflitto rilevato: nessun file verrebbe sovrascritto.")

    with st.expander(f"Anteprima destinazioni ({len(labels)})", expanded=False):
        st.markdown("\n".join(f"- `{x}`" for x in sorted(labels)))


def resolve_overwrite_choice(conflicts: Sequence[str], user_requested: bool) -> bool:
    """
    Determina se abilitare davvero la sovrascrittura dei PDF gia presenti.

    Manteniamo l'operazione opt-in e consentita solo quando esistono conflitti.
    """
    if not conflicts:
        return False
    return bool(user_requested)


def execute_drive_download(
    slug: str,
    conflicts: Sequence[str],
    *,
    download_with_progress: Optional[Callable[..., Sequence[str]]],
    download_simple: Optional[Callable[..., Sequence[str]]],
    invalidate_index: Optional[Callable[[str], None]],
    logger: Any,
    st: StreamlitLike,
    status_guard: StatusGuard,
    overwrite_requested: bool = False,
) -> bool:
    download_fn = download_with_progress or download_simple
    if download_fn is None:
        raise RuntimeError("Funzione di download non disponibile.")

    overwrite_existing = resolve_overwrite_choice(conflicts, overwrite_requested)
    if conflicts and not overwrite_existing:
        st.warning(
            "Sono stati rilevati conflitti con file locali. Verranno scaricati solo i PDF mancanti "
            "finché non li rimuovi o abiliti la sovrascrittura.",
        )

    try:
        with status_guard(
            "Scarico file da Drive...",
            expanded=True,
            error_label="Errore durante il download",
        ) as status_widget:
            call_args: dict[str, Any] = {
                "slug": slug,
                "overwrite": overwrite_existing,
                "require_env": True,
            }
            paths = call_strict(download_fn, logger=logger, **call_args)
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
    except PipelineError as exc:
        message = str(exc)
        if "Download completato con errori" not in message:
            try:
                logger.exception(
                    "ui.manage.drive.download_failed",
                    extra={
                        "slug": slug,
                        "overwrite": overwrite_existing,
                        "error": message,
                    },
                )
            except Exception:
                pass
            st.error(f"Errore durante il download: {exc}")
            return False
        try:
            logger.warning(
                "ui.manage.drive.download_partial",
                extra={"slug": slug, "overwrite": overwrite_existing, "error": message},
            )
        except Exception:
            pass
        try:
            if invalidate_index is not None:
                invalidate_index(slug)
        except Exception:
            pass
        st.warning(f"Download completato con avvisi: {message}")
        return True
    except Exception as exc:
        try:
            logger.exception(
                "ui.manage.drive.download_failed",
                extra={
                    "slug": slug,
                    "overwrite": overwrite_existing,
                    "error": str(exc),
                },
            )
        except Exception:
            pass
        st.error(f"Errore durante il download: {exc}")
        return False


def render_drive_status_message(st: StreamlitLike, disabled: bool, message: str) -> None:
    if disabled:
        st.info(message)
