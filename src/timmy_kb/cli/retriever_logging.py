# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from typing import Any, Mapping

from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("timmy_kb.retriever")
_FALLBACK_LOG = get_structured_logger("timmy_kb.retriever.fallback")


def _safe_log(level: str, event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    """Logging strutturato con fallback deterministico in caso di failure del logger."""
    payload = dict(extra or {})

    # 1) Logger primario
    try:
        log_fn = getattr(LOGGER, level, None)
        if callable(log_fn):
            log_fn(event, extra=payload)
            return
    except Exception as exc:  # pragma: no cover - best-effort
        _FALLBACK_LOG.warning(
            "retriever.log_failed",
            extra={"event": event, "level": level, "stage": "primary", "error": repr(exc)},
        )

    # 2) Logger fallback (stesso schema)
    try:
        fallback_fn = getattr(_FALLBACK_LOG, level, None)
        if callable(fallback_fn):
            fallback_fn(event, extra=payload)
            return
    except Exception as exc:  # pragma: no cover - ultima risorsa
        _FALLBACK_LOG.warning(
            "retriever.log_failed",
            extra={"event": event, "level": level, "stage": "fallback", "error": repr(exc)},
        )

    # 3) Ultima linea di difesa: stderr
    try:
        sys.stderr.write(f"[timmy_kb.retriever.log_failed] level={level} event={event} extra={payload!r}\n")
    except Exception:  # pragma: no cover - fallback finale
        return


def _safe_info(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    _safe_log("info", event, extra=extra)


def _safe_warning(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    _safe_log("warning", event, extra=extra)


def _safe_debug(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    _safe_log("debug", event, extra=extra)
