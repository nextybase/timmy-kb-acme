# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from pipeline.drive.download_steps import DriveCandidate
from ui.manage import drive
from ui.services import drive_runner


class _StreamlitStub:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.toasts: List[str] = []
        self.warnings: List[str] = []

    def toast(self, message: str) -> None:
        self.toasts.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


class _StatusStub:
    def __init__(self) -> None:
        self.updates: List[Dict[str, Any]] = []

    def __enter__(self) -> "_StatusStub":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def test_prepare_download_plan_requires_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drive, "call_best_effort", lambda *_, **__: ["only"])
    with pytest.raises(RuntimeError):
        drive.prepare_download_plan(lambda **_: [], slug="demo", logger=object())


def test_execute_drive_download_respects_require_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: List[Dict[str, Any]] = []

    def fake_call_best_effort(fn, *, logger, **kwargs):
        captured.append(kwargs)
        return ["ok"]

    monkeypatch.setattr(drive, "call_best_effort", fake_call_best_effort)

    def status_guard(*_args: Any, **_kwargs: Any) -> _StatusStub:
        return _StatusStub()

    st_stub = _StreamlitStub()
    invalidate_called: Dict[str, Any] = {}

    def invalidate(slug: str) -> None:
        invalidate_called["slug"] = slug

    def download_with_env(*, slug: str, overwrite: bool, require_env: bool = True):
        return ["a"]

    ok = drive.execute_drive_download(
        slug="demo",
        conflicts=[],
        download_with_progress=download_with_env,
        download_simple=None,
        invalidate_index=invalidate,
        logger=object(),
        st=st_stub,
        status_guard=status_guard,
    )

    assert ok is True
    assert captured[0]["require_env"] is True
    assert captured[0]["overwrite"] is False
    assert invalidate_called.get("slug") == "demo"
    assert st_stub.toasts

    captured.clear()

    def download_simple(*, slug: str, overwrite: bool) -> List[str]:
        return ["b"]

    ok2 = drive.execute_drive_download(
        slug="demo",
        conflicts=[],
        download_with_progress=None,
        download_simple=download_simple,
        invalidate_index=invalidate,
        logger=object(),
        st=st_stub,
        status_guard=status_guard,
    )

    assert ok2 is True
    assert captured[0]["overwrite"] is False
    assert "require_env" not in captured[0]


def test_execute_drive_download_conflicts_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: List[Dict[str, Any]] = []

    def fake_call_best_effort(fn, *, logger, **kwargs):
        captured.append(kwargs)
        return ["ok"]

    monkeypatch.setattr(drive, "call_best_effort", fake_call_best_effort)

    def status_guard(*_args: Any, **_kwargs: Any) -> _StatusStub:
        return _StatusStub()

    st_stub = _StreamlitStub()

    def download_with_env(*, slug: str, overwrite: bool, require_env: bool = True):
        return ["a"]

    ok = drive.execute_drive_download(
        slug="demo",
        conflicts=["raw/x.pdf"],
        download_with_progress=download_with_env,
        download_simple=None,
        invalidate_index=None,
        logger=object(),
        st=st_stub,
        status_guard=status_guard,
        overwrite_requested=False,
    )

    assert ok is True
    assert captured[0]["overwrite"] is False
    assert st_stub.warnings

    captured.clear()
    st_stub.warnings.clear()

    ok_force = drive.execute_drive_download(
        slug="demo",
        conflicts=["raw/x.pdf"],
        download_with_progress=download_with_env,
        download_simple=None,
        invalidate_index=None,
        logger=object(),
        st=st_stub,
        status_guard=status_guard,
        overwrite_requested=True,
    )

    assert ok_force is True
    assert captured[0]["overwrite"] is True
    assert not st_stub.warnings


def test_plan_raw_download_uses_discover_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    raw_dir = workspace_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = raw_dir / "existing.pdf"
    existing.write_text("x", encoding="utf-8")
    new_dest = raw_dir / "sub" / "new.pdf"

    candidates = [
        DriveCandidate(
            category="",
            filename="existing.pdf",
            destination=existing,
            remote_id="1",
            remote_size=10,
            metadata={},
        ),
        DriveCandidate(
            category="sub",
            filename="new.pdf",
            destination=new_dest,
            remote_id="2",
            remote_size=20,
            metadata={},
        ),
    ]

    recorded_kwargs: Dict[str, Any] = {}

    def fake_discover_candidates(**kwargs: Any) -> List[DriveCandidate]:
        recorded_kwargs.update(kwargs)
        return candidates

    ctx = SimpleNamespace(env={"DRIVE_ID": "root-id"})
    monkeypatch.setattr(drive_runner, "get_client_context", lambda *_, **__: ctx)
    monkeypatch.setattr(drive_runner, "get_drive_service", lambda *_: object())
    monkeypatch.setattr(drive_runner, "create_drive_folder", lambda *_a, **_k: None)
    monkeypatch.setattr(drive_runner, "_get_existing_client_folder_id", lambda *_a, **_k: "client-id")
    monkeypatch.setattr(
        drive_runner,
        "_drive_list_folders",
        lambda *_a, **_k: [{"name": "raw", "id": "raw-id"}],
    )
    monkeypatch.setattr(drive_runner, "_drive_list_pdfs", lambda *_a, **_k: [])
    monkeypatch.setattr(drive_runner, "_resolve_workspace", lambda *_a, **_k: workspace_dir)
    monkeypatch.setattr(drive_runner, "discover_candidates", fake_discover_candidates)

    conflicts, labels = drive_runner.plan_raw_download("demo", require_env=False)

    assert conflicts == ["existing.pdf"]
    assert labels == ["existing.pdf", "sub/new.pdf"]
    assert recorded_kwargs.get("local_root") == raw_dir
