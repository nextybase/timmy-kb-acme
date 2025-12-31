# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from pipeline.env_utils import get_int
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.api import get_paths
from semantic.book_readiness import is_book_ready
from ui.clients_store import get_state
from ui.constants import SEMANTIC_READY_STATES
from ui.errors import to_user_message
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button
from ui.utils.workspace import raw_ready, tagging_ready

st = get_streamlit()

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PREVIEW_LOG_DIR = REPO_ROOT / "logs" / "preview"

from pipeline.logging_utils import get_structured_logger, tail_path
from ui.chrome import render_chrome_then_require
from ui.utils.context_cache import get_client_context
from ui.utils.status import status_guard

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any  # type: ignore[misc]

_PREVIEW_MODE = os.getenv("PREVIEW_MODE", "").strip().lower()
StartPreviewFn = Callable[[Any, logging.Logger], str]
StopPreviewFn = Callable[[logging.Logger, Optional[str]], None]

_START_PREVIEW: StartPreviewFn | None = None
_STOP_PREVIEW: StopPreviewFn | None = None


def _load_preview_impl() -> bool:
    """Import lazy degli adapter preview per evitare side-effect a import-time."""
    global _START_PREVIEW, _STOP_PREVIEW, _PREVIEW_MODE
    if _PREVIEW_MODE == "stub":
        return False
    if _START_PREVIEW and _STOP_PREVIEW:
        return True
    try:
        from adapters.preview import start_preview as _sp
        from adapters.preview import stop_preview as _xp
    except Exception:
        _PREVIEW_MODE = "stub"
        return False
    _START_PREVIEW, _STOP_PREVIEW = _sp, _xp
    return True


def _start_preview(ctx: ClientContext, logger: logging.Logger, status_widget: Any) -> str:
    if _load_preview_impl():
        if _START_PREVIEW is None:
            return _start_preview_stub(ctx, logger, status_widget)
        name = _START_PREVIEW(ctx, logger)
        if status_widget is not None and hasattr(status_widget, "update"):
            status_widget.update(label=f"Preview avviata ({name}).", state="complete")
        return name
    return _start_preview_stub(ctx, logger, status_widget)


def _stop_preview(logger: logging.Logger, container_name: Optional[str], status_widget: Any) -> None:
    if _load_preview_impl():
        if _STOP_PREVIEW is None:
            return
        _STOP_PREVIEW(logger, container_name)
        if status_widget is not None and hasattr(status_widget, "update"):
            status_widget.update(label="Preview arrestata.", state="complete")
        return
    _stop_preview_stub(logger, container_name, status_widget)


def _preview_stub_warning(message: str, *, error: Exception | None = None, base: Path | None = None) -> None:
    details: list[str] = []
    if base is not None:
        details.append(f"path={base}")
    if error is not None:
        details.append(f"reason={error}")
    decorated = f"{message} ({'; '.join(details)})" if details else message
    try:
        st.warning(decorated)
    except Exception:
        pass
    try:
        logger = get_structured_logger("ui.preview.stub")
        logger.warning(
            "ui.preview.stub_log_dir_fallback",
            extra={
                "detail": message,
                "error": str(error) if error else "",
                "base": str(base) if base else "",
            },
        )
    except Exception:
        pass


def _resolve_preview_dir(base_setting: Path) -> Path:
    if base_setting.is_absolute():
        guard = base_setting
        candidate = base_setting
    else:
        guard = REPO_ROOT
        candidate = REPO_ROOT / base_setting
    return Path(ensure_within_and_resolve(guard, candidate))


def _preview_log_path(slug: str) -> Path:
    base_setting = Path(os.getenv("PREVIEW_LOG_DIR", "logs/preview"))
    try:
        safe_dir = _resolve_preview_dir(base_setting)
    except Exception as exc:
        fallback_msg = (
            "Percorso personalizzato per i log preview non valido. "
            f"Uso il percorso predefinito {DEFAULT_PREVIEW_LOG_DIR}."
        )
        _preview_stub_warning(fallback_msg, error=exc, base=base_setting)
        safe_dir = DEFAULT_PREVIEW_LOG_DIR
    try:
        safe_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        fallback_dir = DEFAULT_PREVIEW_LOG_DIR
        if safe_dir != fallback_dir:
            fallback_msg = (
                "Impossibile creare la directory personalizzata per i log preview. "
                f"Uso il percorso predefinito {fallback_dir}."
            )
            _preview_stub_warning(fallback_msg, error=exc, base=safe_dir)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        safe_dir = fallback_dir
    return Path(ensure_within_and_resolve(safe_dir, safe_dir / f"{slug}.log"))


def _write_stub_log(slug: str, action: str) -> None:
    log_path = _preview_log_path(slug)
    try:
        existing = read_text_safe(log_path.parent, log_path, encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    payload = existing + f"PREVIEW_STUB_{action.upper()}\n"
    safe_write_text(log_path, payload, encoding="utf-8", atomic=True)


def _start_preview_stub(ctx: ClientContext, logger: logging.Logger, status_widget: Any) -> str:
    slug = getattr(ctx, "slug", "unknown")
    _write_stub_log(slug, "start")
    if status_widget is not None and hasattr(status_widget, "update"):
        status_widget.update(label="Preview avviata (stub).", state="complete")
    try:
        logger.info("ui.preview.stub_started", extra={"slug": slug})
    except Exception:
        pass
    return f"stub-{slug}"


def _stop_preview_stub(logger: logging.Logger, container_name: Optional[str], status_widget: Any) -> None:
    slug = (container_name or "unknown").split("stub-")[-1].strip()
    _write_stub_log(slug, "stop")
    if status_widget is not None and hasattr(status_widget, "update"):
        status_widget.update(label="Preview arrestata (stub).", state="complete")
    try:
        logger.info("ui.preview.stub_stopped", extra={"slug": slug})
    except Exception:
        pass


st.subheader("Preview Docker (HonKit)")

slug = render_chrome_then_require()

try:
    ctx = get_client_context(slug, interactive=False, require_env=False)
    logger = get_structured_logger("ui.preview", context=ctx)
except Exception as exc:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)
else:
    book_dir: Path | None = None
    book_ready = False
    raw_ok = False
    tagging_ok = False
    try:
        candidate_dir = getattr(ctx, "md_dir", None)
        if candidate_dir is None:
            candidate_dir = get_paths(slug)["book"]
        book_dir = candidate_dir
        if isinstance(book_dir, Path):
            book_ready = is_book_ready(book_dir)
    except Exception:
        book_ready = False
    try:
        state_value = get_state(slug) or ""
        state_norm = state_value.strip().lower()
        semantic_ready = state_norm in SEMANTIC_READY_STATES
    except Exception:
        state_norm = ""
        semantic_ready = False
    try:
        raw_ok, _ = raw_ready(slug)
        tagging_ok, _ = tagging_ready(slug)
    except Exception:
        raw_ok = False
        tagging_ok = False
    can_preview = raw_ok and tagging_ok and semantic_ready and book_ready
    if not can_preview:
        st.info(
            "Anteprima disponibile dopo l'arricchimento semantico e con la cartella "
            "book/ completa (README, SUMMARY e file Markdown di contenuto)."
        )
        book_tail = tail_path(book_dir) if book_dir else ""
        st.caption(
            f"Stato cliente: {state_norm or 'n/d'} · Book pronta: {'sì' if book_ready else 'no'}"
            + (f" (cartella: {book_tail})" if book_tail else "")
        )
        try:
            logger.info(
                "ui.preview.not_ready",
                extra={
                    "slug": slug,
                    "raw_ready": raw_ok,
                    "tagging_ready": tagging_ok,
                    "book_ready": book_ready,
                    "semantic_ready": semantic_ready,
                    "state": state_norm,
                    "book_path": book_tail,
                },
            )
        except Exception:  # pragma: no cover - logging best effort
            pass
        st.session_state.pop("preview_container", None)

    else:
        col_start, col_stop = st.columns(2)
        if _column_button(col_start, "Avvia preview", key="btn_preview_start"):
            try:
                with status_guard(
                    "Avvio la preview...",
                    expanded=True,
                    error_label="Errore durante l'avvio della preview",
                ) as status:
                    name = _start_preview(ctx, logger, status)
                    st.session_state["preview_container"] = name
            except Exception as exc:
                title, body, caption = to_user_message(exc)
                st.error(title)
                if caption or body:
                    st.caption(caption or body)
                try:
                    logger.exception(
                        "ui.preview.start_failed",
                        extra={"slug": slug, "error": str(exc)},
                    )
                except Exception:
                    pass
        if _column_button(col_stop, "Arresta preview", key="btn_preview_stop"):
            try:
                with status_guard(
                    "Arresto la preview...",
                    expanded=True,
                    error_label="Errore durante l'arresto della preview",
                ) as status:
                    _stop_preview(logger, st.session_state.get("preview_container"), status)
                    st.session_state.pop("preview_container", None)
            except Exception as exc:
                title, body, caption = to_user_message(exc)
                st.error(title)
                if caption or body:
                    st.caption(caption or body)
                try:
                    logger.exception(
                        "ui.preview.stop_failed",
                        extra={"slug": slug, "error": str(exc)},
                    )
                except Exception:
                    pass
        host_port = get_int("PREVIEW_PORT", 4000) or 4000
        preview_url = f"http://localhost:{host_port}"
        st.caption("Quando la preview è attiva, aprila in un'altra scheda:")
        try:
            st.code(preview_url, language="bash")
        except Exception:
            st.write(preview_url)
        link_fn = getattr(st, "link_button", None)
        if callable(link_fn):
            try:
                link_fn("Apri anteprima HonKit", preview_url, type="primary")
            except Exception:
                pass
