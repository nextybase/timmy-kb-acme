from __future__ import annotations

import importlib
import logging
import shutil
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.ui.test_manage_probe_raw import register_streamlit_runtime


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.button_returns: dict[str, bool] = {}
        self.success_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []
        self.html_calls: list[str] = []
        self.rerun_called = 0

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def text_input(self, _label: str, *, value: str = "", **_kwargs: Any) -> str:
        return value

    def file_uploader(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    def button(self, label: str, *_args: Any, **_kwargs: Any) -> bool:
        return self.button_returns.get(label, False)

    def warning(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.warning_messages.append(message)

    def success(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.success_messages.append(message)

    def error(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.error_messages.append(message)

    def spinner(self, *_args: Any, **_kwargs: Any):
        return _status_stub()

    def container(self, *_args: Any, **_kwargs: Any):
        return _status_stub()

    def status(self, *_args: Any, **_kwargs: Any):
        return _status_stub()

    def progress(self, *_args: Any, **_kwargs: Any):
        class _Progress:
            def progress(self, *_p_args: Any, **_p_kwargs: Any) -> None:
                return None

        return _Progress()

    def empty(self, *_args: Any, **_kwargs: Any):
        class _Empty:
            def markdown(self, *_m_args: Any, **_m_kwargs: Any) -> None:
                return None

        return _Empty()

    def html(self, markup: str, *_args: Any, **_kwargs: Any) -> None:
        self.html_calls.append(markup)

    def stop(self) -> None:
        raise RuntimeError("st.stop non dovrebbe essere invocato in fallback locale")

    def rerun(self) -> None:
        self.rerun_called += 1


@contextmanager
def _status_stub() -> Iterator[Any]:
    class _Ctx:
        def update(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    yield _Ctx()


def _make_pdf_stub(payload: bytes) -> Any:
    class _Pdf:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def getvalue(self) -> bytes:
            return self._data

    return _Pdf(payload)


def test_init_workspace_skips_drive_when_helper_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    slug = "dummy"
    monkeypatch.chdir(tmp_path)
    client_root = tmp_path / "output" / f"timmy-kb-{slug}"
    if client_root.exists():
        shutil.rmtree(client_root)

    stub = _StreamlitStub()
    stub.button_returns = {"Inizializza Workspace": True}
    stub.session_state = {"new_client.phase": "init", "new_client.slug": "", "client_name": ""}
    stub.text_input = lambda label, **kwargs: "dummy" if "Slug" in label else kwargs.get("value", "")
    stub.file_uploader = lambda *_args, **_kwargs: _make_pdf_stub(b"%PDF-1.4")

    monkeypatch.setenv("UI_ALLOW_LOCAL_ONLY", "true")
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)

    fake_drive_module = types.ModuleType("ui.services.drive_runner")
    monkeypatch.setitem(sys.modules, "ui.services.drive_runner", fake_drive_module)

    import timmykb.pre_onboarding as pre_onboarding

    def _fake_bootstrap(slug: str, *, client_name: str | None, vision_statement_pdf: bytes | None) -> None:
        base = client_root
        (base / "config").mkdir(parents=True, exist_ok=True)
        (base / "config" / "config.yaml").write_text("client_name: Dummy\n", encoding="utf-8")
        (base / "semantic").mkdir(parents=True, exist_ok=True)
        if vision_statement_pdf:
            (base / "config" / "VisionStatement.pdf").write_bytes(vision_statement_pdf)

    monkeypatch.setattr(pre_onboarding, "ensure_local_workspace_for_ui", _fake_bootstrap, raising=True)

    import ui.services.vision_provision as vision_mod

    def _fake_run_vision(ctx: Any, *, slug: str, pdf_path: Path, logger: Any | None = None, **_: Any) -> None:
        semantic_dir = Path(ctx.base_dir) / "semantic"
        semantic_dir.mkdir(parents=True, exist_ok=True)
        (semantic_dir / "semantic_mapping.yaml").write_text("version: 1\n", encoding="utf-8")
        (semantic_dir / "cartelle_raw.yaml").write_text("version: 1\n", encoding="utf-8")

    monkeypatch.setattr(vision_mod, "run_vision", _fake_run_vision, raising=True)

    sys.modules.pop("ui.utils.status", None)
    import ui.utils.status as status_mod

    monkeypatch.setattr(status_mod, "status_guard", lambda *a, **k: _status_stub(), raising=True)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        sys.modules.pop("src.ui.pages.new_client", None)
        import timmykb.ui.pages.new_client as new_client

        importlib.reload(new_client)

    try:
        assert stub.success_messages
        assert not stub.error_messages
        assert stub.session_state.get("new_client.phase") == "ready_to_open"
        assert stub.session_state.get("new_client.slug") == slug
        assert any("ui.drive.provisioning_skipped" in record.getMessage() for record in caplog.records)
    finally:
        if client_root.exists():
            shutil.rmtree(client_root)
