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
                return None

            return _stop
        if name == "rerun":

            def _rerun(*_a: Any, **_k: Any) -> None:
                return None

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

    def reset(self) -> None:
        self.session_state.clear()
        self.query_params.clear()
        self.sidebar = _FunctionStub()


_STUB: StreamlitStub | None = None


def _get_stub() -> StreamlitStub:
    global _STUB
    if _STUB is None:
        _STUB = StreamlitStub()
    return _STUB


def get_streamlit() -> Any:
    """Restituisce il modulo streamlit oppure lo stub riutilizzabile."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        # Se non c'è un contesto streamlit attivo (pytest/headless), usa lo stub
        if get_script_run_ctx() is None and hasattr(st, "__file__"):
            raise RuntimeError("streamlit runtime non attivo")
        return st
    except Exception:
        return cast(Any, _get_stub())


def reset_streamlit_stub() -> None:
    """Reinizializza lo stub condiviso (usato nei test per evitare stato residuo)."""
    if _STUB is not None:
        _STUB.reset()
