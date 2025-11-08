# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ui.manage import drive


class _StreamlitStub:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.toasts: List[str] = []

    def toast(self, message: str) -> None:
        self.toasts.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


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
    assert "require_env" not in captured[0]
