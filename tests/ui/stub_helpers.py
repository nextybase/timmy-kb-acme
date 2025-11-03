# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sys
import types
from typing import Any, Callable, TypeVar

import pytest

from .streamlit_stub import StreamlitStub

F = TypeVar("F", bound=Callable[..., Any])


def _cache_decorator(func: F | None = None, **_kwargs: Any) -> F | Callable[[F], F]:
    def _wrap(inner: F) -> F:
        return inner

    if callable(func):
        return func
    return _wrap


def install_streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> StreamlitStub:
    """Registra lo StreamlitStub e il runtime minimo necessario per importare le pagine UI."""
    stub = StreamlitStub()

    streamlit_module = types.ModuleType("streamlit")
    for name in [
        "button",
        "columns",
        "status",
        "spinner",
        "subheader",
        "error",
        "caption",
        "warning",
        "info",
        "success",
        "toast",
        "checkbox",
        "toggle",
        "radio",
        "number_input",
        "selectbox",
        "text_input",
        "text_area",
        "form",
        "form_submit_button",
        "dialog",
        "container",
        "expander",
        "page_link",
        "link_button",
        "markdown",
        "html",
        "code",
        "write",
        "file_uploader",
    ]:
        setattr(streamlit_module, name, getattr(stub, name))

    setattr(streamlit_module, "session_state", stub.session_state)
    setattr(streamlit_module, "query_params", stub.query_params)
    setattr(streamlit_module, "rerun", stub.rerun)
    setattr(streamlit_module, "stop", stub.stop)
    setattr(streamlit_module, "experimental_rerun", stub.rerun)
    setattr(streamlit_module, "experimental_set_query_params", lambda **_kwargs: None)
    setattr(streamlit_module, "cache_data", _cache_decorator)
    setattr(streamlit_module, "cache_resource", _cache_decorator)
    setattr(streamlit_module, "memoize", _cache_decorator)

    class _FragmentRunner:
        def __call__(self, fn=None):
            if fn is None:

                def _decorator(inner):
                    return self(inner)

                return _decorator

            def _runner():
                return fn()

            return _runner

    def _fragment(name: str | None = None):  # type: ignore[unused-argument]
        runner = _FragmentRunner()
        if name is None or callable(name):
            # Support usage either as decorator or function-style.
            return runner(name) if callable(name) else runner
        return runner

    setattr(streamlit_module, "fragment", _fragment)

    _register_runtime(monkeypatch, stub)

    monkeypatch.setitem(sys.modules, "streamlit", streamlit_module)

    try:
        import ui.utils.streamlit_fragments as streamlit_fragments

        monkeypatch.setattr(streamlit_fragments, "_FRAGMENT", _fragment, raising=False)
    except Exception:
        pass
    return stub


def _register_runtime(monkeypatch: pytest.MonkeyPatch, stub: StreamlitStub) -> None:
    runtime_module = types.ModuleType("streamlit.runtime")
    caching_module = types.ModuleType("streamlit.runtime.caching")
    caching_module.cache_data = _cache_decorator  # type: ignore[attr-defined]
    caching_module.cache_resource = _cache_decorator  # type: ignore[attr-defined]
    caching_module.memoize = _cache_decorator  # type: ignore[attr-defined]

    scriptrunner_module = types.ModuleType("streamlit.runtime.scriptrunner")

    def _get_script_run_ctx(*_args: Any, **_kwargs: Any) -> None:
        return None

    scriptrunner_module.get_script_run_ctx = _get_script_run_ctx  # type: ignore[attr-defined]
    scriptrunner_module.script_run_context = types.SimpleNamespace(  # type: ignore[attr-defined]
        get_script_run_ctx=_get_script_run_ctx
    )

    script_runner_module = types.ModuleType("streamlit.runtime.scriptrunner.script_runner")

    class _RerunException(Exception):
        pass

    script_runner_module.RerunException = _RerunException  # type: ignore[attr-defined]
    scriptrunner_module.script_runner = script_runner_module  # type: ignore[attr-defined]

    runtime_module.caching = caching_module  # type: ignore[attr-defined]
    runtime_module.scriptrunner = scriptrunner_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "streamlit.runtime", runtime_module)
    monkeypatch.setitem(sys.modules, "streamlit.runtime.caching", caching_module)
    monkeypatch.setitem(sys.modules, "streamlit.runtime.scriptrunner", scriptrunner_module)
    monkeypatch.setitem(
        sys.modules,
        "streamlit.runtime.scriptrunner.script_runner",
        script_runner_module,
    )

    setattr(stub, "runtime", runtime_module)
