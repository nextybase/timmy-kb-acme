# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import pytest

from ui.pages import diagnostics as page


class _StreamlitStub:
    def __init__(self) -> None:
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.code_calls: list[Any] = []
        self.download_calls: list[tuple[str, dict[str, Any]]] = []
        self.json_payloads: list[dict[str, Any]] = []
        self.captions: list[str] = []

    @contextmanager
    def expander(self, _label: str, *, expanded: bool = False):
        yield

    def info(self, message: str) -> None:
        self.info_calls.append(message)

    def warning(self, message: str) -> None:
        self.warning_calls.append(message)

    def code(self, value: Any) -> None:
        self.code_calls.append(value)

    def download_button(self, label: str, **kwargs: Any) -> None:
        self.download_calls.append((label, kwargs))

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def json(self, payload: dict[str, Any]) -> None:
        self.json_payloads.append(payload)


@pytest.fixture()
def streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> _StreamlitStub:
    stub = _StreamlitStub()
    monkeypatch.setattr(page, "st", stub)
    return stub


def test_render_logs_renders_workspace_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, streamlit_stub: _StreamlitStub
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "log0.txt"
    log_file.write_text("hello", encoding="utf-8")
    log_files = [log_file]

    monkeypatch.setattr(page.diag, "collect_log_files", lambda _base: log_files)
    monkeypatch.setattr(page.diag, "get_safe_reader", lambda: None)
    monkeypatch.setattr(page.diag, "tail_log_bytes", lambda *_args, **_kwargs: b"log")
    monkeypatch.setattr(page.diag, "build_logs_archive", lambda *_args, **_kwargs: b"zip")

    summary_payload = {"slug": "dummy", "log_files": ["log0.txt"], "counts": {"raw": (0, False)}}

    def _build_summary(slug: str, files: list[Path], *, base_dir: Optional[Path] = None):
        assert slug == "dummy"
        assert files == log_files
        assert base_dir == tmp_path
        return summary_payload

    monkeypatch.setattr(page.diag, "build_workspace_summary", _build_summary)

    page._render_logs(tmp_path, "dummy")

    assert streamlit_stub.json_payloads[-1] is summary_payload
    assert any("Workspace summary" in caption for caption in streamlit_stub.captions)
    assert streamlit_stub.download_calls, "Il pulsante download deve essere mostrato"


def test_render_logs_handles_missing_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, streamlit_stub: _StreamlitStub
) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "log0.txt"
    log_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(page.diag, "collect_log_files", lambda _base: [log_file])
    monkeypatch.setattr(page.diag, "get_safe_reader", lambda: None)
    monkeypatch.setattr(page.diag, "tail_log_bytes", lambda *_args, **_kwargs: b"log")
    monkeypatch.setattr(page.diag, "build_logs_archive", lambda *_args, **_kwargs: b"zip")
    monkeypatch.setattr(page.diag, "build_workspace_summary", lambda *_args, **_kwargs: None)

    page._render_logs(tmp_path, "dummy")

    assert not streamlit_stub.json_payloads, "Il summary non deve essere renderizzato quando assente"
