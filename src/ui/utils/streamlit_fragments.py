# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar, cast

from pipeline.logging_utils import get_structured_logger

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = cast(Any, None)

try:
    from streamlit import fragment as _fragment_impl
except Exception:  # pragma: no cover
    _fragment_impl = None

FragmentCallable = Callable[[Callable[[], None]], Callable[[], None]]
_FRAGMENT: Optional[FragmentCallable] = cast(Optional[FragmentCallable], _fragment_impl)

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
    try:
        log.exception(event, extra=log_extra)
    except Exception:
        pass

    if st is None:
        return

    try:
        st.error(message)
        if show_details:
            with st.expander(expander_label, expanded=False):
                st.exception(exc)
    except Exception:
        pass


def run_fragment(key: str, body: Callable[[], T]) -> T:
    """Execute `body` inside a Streamlit fragment when available and return its result."""
    if _FRAGMENT is not None:
        sentinel = object()
        box: dict[str, object | T] = {"value": sentinel}

        def _wrapped() -> None:
            box["value"] = body()

        safe_key = key.replace("/", "_").replace(".", "_")
        _wrapped.__name__ = f"fragment_{safe_key}"
        _wrapped.__qualname__ = _wrapped.__name__
        runner = _FRAGMENT(_wrapped)
        runner()
        value = box["value"]
        if value is sentinel:  # pragma: no cover - should not happen
            raise RuntimeError("Streamlit fragment did not execute the body")
        return cast(T, value)
    return body()
