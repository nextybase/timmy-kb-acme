# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

import streamlit as st
from streamlit import fragment as _fragment

from pipeline.logging_utils import get_structured_logger

T = TypeVar("T")


def show_error_with_details(
    logger: Any | None,
    message: str,
    exc: BaseException,
    *,
    event: str = "ui.error",
    extra: dict[str, object] | None = None,
    show_details: bool = False,
    expander_label: str = "Dettagli tecnici",
) -> None:
    """Renderizza un messaggio sintetico e registra il dettaglio sui log."""
    log = logger or get_structured_logger(event)
    log_extra: dict[str, object] = {"error": str(exc), "exception_type": type(exc).__name__}
    if extra:
        log_extra.update(extra)

    log.exception(event, extra=log_extra)

    st.error(message)
    if show_details:
        with st.expander(expander_label, expanded=False):
            st.exception(exc)


def run_fragment(key: str, body: Callable[[], T]) -> T:
    """Esegue body dentro un frammento Streamlit e ne restituisce il risultato."""
    sentinel = object()
    box: dict[str, object | T] = {"value": sentinel}

    def _wrapped() -> None:
        box["value"] = body()

    safe_key = key.replace("/", "_").replace(".", "_")
    _wrapped.__name__ = f"fragment_{safe_key}"
    _wrapped.__qualname__ = _wrapped.__name__

    runner = _fragment(_wrapped)
    runner()

    value = box["value"]
    if value is sentinel:  # pragma: no cover - should not happen
        raise RuntimeError("Streamlit fragment did not execute the body")
    return cast(T, value)


__all__ = ["run_fragment", "show_error_with_details"]
