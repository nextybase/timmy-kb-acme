# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import inspect
from typing import Any, Callable, ContextManager, Optional, Protocol, Sequence, cast

from ui.manage._helpers import call_best_effort


class StreamlitLike(Protocol):
    def expander(self, label: str, *, expanded: bool = ...) -> ContextManager[Any]: ...

    def markdown(self, body: str) -> Any: ...

    def info(self, body: str) -> Any: ...

    def toast(self, body: str) -> Any: ...

    def error(self, body: str) -> Any: ...

    def warning(self, body: str) -> Any: ...


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
    result = cast(Sequence[Sequence[str]], call_best_effort(plan_fn, logger=logger, slug=slug, require_env=True))
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
            }
            try:
                signature = inspect.signature(download_fn)
            except (TypeError, ValueError):
                signature = None
            if signature and "require_env" in signature.parameters:
                call_args["require_env"] = True
            paths = call_best_effort(download_fn, logger=logger, **call_args)
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
