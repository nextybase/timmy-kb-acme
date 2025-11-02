# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/preview.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional, cast

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.clients_store import get_state
from ui.constants import SEMANTIC_READY_STATES
from ui.errors import to_user_message
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button
from ui.utils.workspace import has_raw_pdfs

st = get_streamlit()

REPO_ROOT = Path(__file__).resolve().parents[3]

from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from ui.chrome import render_chrome_then_require
from ui.utils.status import status_guard

_PREVIEW_MODE = os.getenv("PREVIEW_MODE", "").strip().lower()

if _PREVIEW_MODE != "stub":  # pragma: no branch - import reale solo se serve
    from adapters.preview import start_preview, stop_preview

    def _start_preview(ctx: ClientContext, logger: logging.Logger, status_widget: Any) -> str:
        name = cast(str, start_preview(ctx, logger))
        if status_widget is not None and hasattr(status_widget, "update"):
            status_widget.update(label=f"Preview avviata ({name}).", state="complete")
        return name

    def _stop_preview(logger: logging.Logger, container_name: Optional[str], status_widget: Any) -> None:
        stop_preview(logger, container_name=container_name)
        if status_widget is not None and hasattr(status_widget, "update"):
            status_widget.update(label="Preview arrestata.", state="complete")

else:

    def _preview_log_path(slug: str) -> Path:
        base_setting = Path(os.getenv("PREVIEW_LOG_DIR", "logs/preview"))
        target_dir = base_setting if base_setting.is_absolute() else REPO_ROOT / base_setting
        safe_dir = Path(ensure_within_and_resolve(REPO_ROOT, target_dir))
        safe_dir.mkdir(parents=True, exist_ok=True)
        return Path(ensure_within_and_resolve(safe_dir, safe_dir / f"{slug}.log"))

    def _write_stub_log(slug: str, action: str) -> None:
        log_path = _preview_log_path(slug)
        try:
            existing = read_text_safe(log_path.parent, log_path, encoding="utf-8")
        except FileNotFoundError:
            existing = ""
        payload = existing + f"PREVIEW_STUB_{action.upper()}\n"
        safe_write_text(log_path, payload, encoding="utf-8", atomic=True)

    def _start_preview(ctx: ClientContext, logger: logging.Logger, status_widget: Any) -> str:
        slug = getattr(ctx, "slug", "unknown")
        _write_stub_log(slug, "start")
        if status_widget is not None and hasattr(status_widget, "update"):
            status_widget.update(label="Preview avviata (stub).", state="complete")
        try:
            logger.info("ui.preview.stub_started", extra={"slug": slug})
        except Exception:
            pass
        return f"stub-{slug}"

    def _stop_preview(logger: logging.Logger, container_name: Optional[str], status_widget: Any) -> None:
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
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    logger = get_structured_logger("ui.preview", context=ctx)
except Exception as exc:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)
else:
    raw_ready = False
    raw_dir: Path | None = None
    try:
        ready, raw_path = has_raw_pdfs(slug)
        raw_ready = bool(ready)
        raw_dir = raw_path if isinstance(raw_path, Path) else None
    except Exception:
        raw_ready = False
    try:
        state_value = get_state(slug) or ""
        state_norm = state_value.strip().lower()
        semantic_ready = state_norm in SEMANTIC_READY_STATES
    except Exception:
        state_norm = ""
        semantic_ready = False
    if not raw_ready or not semantic_ready:
        st.info("Anteprima disponibile dopo l'arricchimento semantico e con PDF presenti in raw/.")
        st.caption(
            f"Stato cliente: {state_norm or 'n/d'} · RAW pronto: {'sì' if raw_ready else 'no'}"
            + (f" (path: {raw_dir})" if raw_dir else "")
        )
        try:
            logger.info(
                "ui.preview.not_ready",
                extra={
                    "slug": slug,
                    "raw_ready": raw_ready,
                    "semantic_ready": semantic_ready,
                    "state": state_norm,
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
