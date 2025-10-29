from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any, Tuple

import pytest

import ui.utils.workspace
from tests.ui.streamlit_stub import StreamlitStub


def register_streamlit_runtime(monkeypatch: pytest.MonkeyPatch, st_stub: StreamlitStub) -> None:
    """Registra moduli runtime di Streamlit necessari per i test UI."""

    def _cache_decorator(func=None, **_kwargs):
        def _wrap(inner):
            return inner

        if callable(func):
            return func
        return _wrap

    runtime_module = types.ModuleType("streamlit.runtime")
    caching_module = types.ModuleType("streamlit.runtime.caching")
    caching_module.cache_data = _cache_decorator  # type: ignore[attr-defined]
    caching_module.cache_resource = _cache_decorator  # type: ignore[attr-defined]
    caching_module.memoize = _cache_decorator  # type: ignore[attr-defined]

    scriptrunner_module = types.ModuleType("streamlit.runtime.scriptrunner")

    def _get_script_run_ctx(*_args: Any, **_kwargs: Any) -> None:
        return None

    scriptrunner_module.get_script_run_ctx = _get_script_run_ctx  # type: ignore[attr-defined]
    scriptrunner_module.script_run_context = types.SimpleNamespace(get_script_run_ctx=_get_script_run_ctx)  # type: ignore[attr-defined]

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
    monkeypatch.setitem(sys.modules, "streamlit.runtime.scriptrunner.script_runner", script_runner_module)
    setattr(st_stub, "runtime", runtime_module)


def _load_manage_module(
    monkeypatch: pytest.MonkeyPatch,
    st_stub: StreamlitStub,
    slug: str,
    has_raw_result: Tuple[bool, str | None],
) -> None:
    monkeypatch.setitem(sys.modules, "streamlit", st_stub)
    register_streamlit_runtime(monkeypatch, st_stub)
    import ui.chrome
    import ui.utils.workspace

    monkeypatch.setattr(ui.chrome, "render_chrome_then_require", lambda allow_without_slug: slug)
    monkeypatch.setattr(ui.utils.workspace, "has_raw_pdfs", lambda _slug: has_raw_result)

    sys.modules.pop("ui.pages.manage", None)
    manage = importlib.import_module("ui.pages.manage")
    monkeypatch.setattr(manage, "_render_drive_tree", None, raising=False)
    monkeypatch.setattr(manage, "_render_drive_diff", None, raising=False)


def test_manage_semantic_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = StreamlitStub()
    raw_path = str(Path("output") / "timmy-kb-dummy" / "raw")
    _load_manage_module(monkeypatch, st_stub, slug="acme", has_raw_result=(True, raw_path))

    assert "Avvia arricchimento semantico" in st_stub.button_calls
    assert any("Arricchimento semantico" in msg for msg in st_stub.info_messages)
    assert not any("PDF rilevati" in msg for msg in st_stub.success_messages)
    expected_warn = "`semantic/tags.db` non trovato: estrai e valida i tag prima dell'arricchimento semantico."
    assert expected_warn in st_stub.warning_messages


def test_iter_pdfs_safe_returns_resolved(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / "raw"
    root.mkdir(parents=True)
    pdf = root / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    try:
        (root / "link.pdf").symlink_to(pdf)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink non supportati su questa piattaforma: {exc}")
    results = list(ui.utils.workspace.iter_pdfs_safe(root))
    assert results == [pdf.resolve()]
