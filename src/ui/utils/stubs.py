# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/stubs.py
from __future__ import annotations

from typing import Any, Literal, cast


class _FunctionStub:
    """No-op callable/context manager usato per simulare le API Streamlit in test/headless."""

    def __call__(self, *args: Any, **kwargs: Any) -> "_FunctionStub":
        return self

    def __enter__(self) -> "_FunctionStub":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return False

    def __getattr__(self, name: str) -> "_FunctionStub":
        return self

    def __bool__(self) -> bool:
        return False


class StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.query_params: dict[str, str] = {}
        self.sidebar = _FunctionStub()

    def __getattr__(self, name: str) -> Any:
        if name == "stop":

            def _stop(*_a: Any, **_k: Any) -> None:
                raise RuntimeError("Streamlit stop non disponibile nel fallback")

            return _stop
        if name == "rerun":

            def _rerun(*_a: Any, **_k: Any) -> None:
                raise RuntimeError("Streamlit rerun non disponibile nel fallback")

            return _rerun
        if name == "spinner":

            class _SpinnerStub:
                def __enter__(self) -> None:
                    return None

                def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
                    return False

            def _spinner(*_a: Any, **_k: Any) -> _SpinnerStub:
                return _SpinnerStub()

            return _spinner
        if name == "columns":

            def _columns(spec: Any) -> tuple[_FunctionStub, ...]:
                try:
                    count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
                except Exception:
                    count = 0
                return tuple(_FunctionStub() for _ in range(max(count, 0)))

            return _columns
        return _FunctionStub()


def get_streamlit() -> Any:
    """Restituisce il modulo streamlit oppure lo stub riutilizzabile."""
    try:
        import streamlit as st

        return st
    except Exception:
        return cast(Any, StreamlitStub())
