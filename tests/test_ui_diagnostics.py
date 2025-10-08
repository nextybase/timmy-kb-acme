from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import List, Tuple

import pytest

if "streamlit.runtime.scriptrunner_utils.exceptions" not in sys.modules:
    rerun_module = types.ModuleType("streamlit.runtime.scriptrunner_utils.exceptions")

    class _DummyRerunException(Exception):
        pass

    rerun_module.RerunException = _DummyRerunException

    scriptrunner_utils = types.ModuleType("streamlit.runtime.scriptrunner_utils")
    scriptrunner_utils.exceptions = rerun_module

    runtime_module = types.ModuleType("streamlit.runtime")
    runtime_module.scriptrunner_utils = scriptrunner_utils

    streamlit_module = types.ModuleType("streamlit")

    class _QueryParams(dict):
        def to_dict(self) -> dict[str, str | list[str]]:
            return dict(self)

        def from_dict(self, mapping: dict[str, str | list[str]]) -> None:
            self.clear()
            self.update(mapping)

        def get_all(self, key: str) -> list[str]:
            value = self.get(key)
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value]

    class _Navigation:
        def __init__(self, pages, position="top"):
            self.pages = pages
            self.position = position

        def run(self) -> None:  # pragma: no cover - behavior irrilevante per i test
            return None

    streamlit_module.Page = lambda path, **kwargs: types.SimpleNamespace(path=path, **kwargs)
    streamlit_module.navigation = lambda pages, position="top": _Navigation(pages, position=position)
    streamlit_module.runtime = runtime_module
    streamlit_module.set_page_config = lambda *a, **k: None
    streamlit_module.error = lambda *a, **k: None
    streamlit_module.info = lambda *a, **k: None
    streamlit_module.success = lambda *a, **k: None
    streamlit_module.warning = lambda *a, **k: None
    streamlit_module.session_state = {}
    streamlit_module.query_params = _QueryParams()
    streamlit_module.sidebar = types.SimpleNamespace(
        markdown=lambda *a, **k: None,
        button=lambda *a, **k: False,
        link_button=lambda *a, **k: None,
        image=lambda *a, **k: None,
    )
    streamlit_module.markdown = lambda *a, **k: None
    streamlit_module.button = lambda *a, **k: False

    sys.modules["streamlit.runtime.scriptrunner_utils.exceptions"] = rerun_module
    sys.modules["streamlit.runtime.scriptrunner_utils"] = scriptrunner_utils
    sys.modules["streamlit.runtime"] = runtime_module
    sys.modules["streamlit"] = streamlit_module

import onboarding_ui as onboarding
import pipeline.context as pipeline_context


class _StubStreamlit:
    def __init__(self) -> None:
        self.calls: List[Tuple] = []
        self.session_state = {}

    def expander(self, label: str, expanded: bool = False):
        self.calls.append(("expander", label, expanded))

        class _Ctx:
            def __enter__(self_inner):
                return self

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    def write(self, value):
        self.calls.append(("write", value))

    def info(self, value):
        self.calls.append(("info", value))

    def code(self, value):
        self.calls.append(("code", value))

    def download_button(self, label: str, **kwargs):
        self.calls.append(("download_button", label, kwargs))
        return None


class _DummyContext:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


@pytest.fixture
def stub_streamlit(monkeypatch) -> _StubStreamlit:
    stub = _StubStreamlit()
    monkeypatch.setattr(onboarding, "st", stub, raising=True)
    return stub


@pytest.fixture
def stub_context_loader(monkeypatch, tmp_path: Path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "app.log"
    with log_path.open("w", encoding="utf-8") as fh:
        for i in range(5000):
            fh.write(f"line-{i}\n")

    dummy_ctx = _DummyContext(base_dir=tmp_path)

    def _load(slug: str, interactive: bool, require_env: bool, run_id):
        return dummy_ctx

    monkeypatch.setattr(pipeline_context.ClientContext, "load", staticmethod(_load), raising=True)
    return log_path


def test_diagnostics_reads_only_tail(stub_streamlit: _StubStreamlit, stub_context_loader: Path):
    _ = stub_context_loader
    onboarding._diagnostics("dummy")

    code_calls = [call for call in stub_streamlit.calls if call[0] == "code"]
    assert code_calls, "_diagnostics non ha mostrato i log"

    shown_text = code_calls[0][1]
    assert "line-0" not in shown_text
    assert "line-4999" in shown_text
    assert len(shown_text) <= 4096


def test_resolve_slug_normalizes_whitespace(stub_streamlit: _StubStreamlit) -> None:
    stub_streamlit.session_state.clear()
    assert onboarding._resolve_slug("  MIXED  ") == "mixed"

    stub_streamlit.session_state["ui.manage.selected_slug"] = "  Secondo  "
    assert onboarding._resolve_slug(None) == "secondo"
