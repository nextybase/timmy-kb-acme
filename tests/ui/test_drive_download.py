# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from tests.ui.streamlit_stub import StreamlitStub
from ui.manage import drive


class _StatusStub:
    def __enter__(self) -> "_StatusStub":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def update(self, **_kwargs: Any) -> None:
        return None


def _status_guard(*_args: Any, **_kwargs: Any) -> _StatusStub:
    return _StatusStub()


def test_drive_download_warns_when_overwrite_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    st = StreamlitStub()
    captured: Dict[str, Any] = {}

    def fake_call_best_effort(fn, *, logger, **kwargs):
        captured.update(kwargs)
        return ["ok"]

    monkeypatch.setattr(drive, "call_best_effort", fake_call_best_effort)

    def download_with_env(*, slug: str, overwrite: bool, require_env: bool = True) -> List[str]:
        return ["a"]

    ok = drive.execute_drive_download(
        slug="dummy",
        conflicts=["raw/existing.pdf"],
        download_with_progress=download_with_env,
        download_simple=None,
        invalidate_index=None,
        logger=object(),
        st=st,
        status_guard=_status_guard,
        overwrite_requested=False,
    )

    assert ok is True
    assert captured["overwrite"] is False
    assert st.warning_messages
    assert "conflitti" in st.warning_messages[0]


def test_drive_download_force_overwrite(monkeypatch: pytest.MonkeyPatch) -> None:
    st = StreamlitStub()
    captured: Dict[str, Any] = {}

    def fake_call_best_effort(fn, *, logger, **kwargs):
        captured.update(kwargs)
        return ["ok"]

    monkeypatch.setattr(drive, "call_best_effort", fake_call_best_effort)

    def download_with_env(*, slug: str, overwrite: bool, require_env: bool = True) -> List[str]:
        return ["a"]

    ok = drive.execute_drive_download(
        slug="dummy",
        conflicts=["raw/existing.pdf"],
        download_with_progress=download_with_env,
        download_simple=None,
        invalidate_index=None,
        logger=object(),
        st=st,
        status_guard=_status_guard,
        overwrite_requested=True,
    )

    assert ok is True
    assert captured["overwrite"] is True
    assert not st.warning_messages


def test_resolve_overwrite_choice_requires_conflicts() -> None:
    assert drive.resolve_overwrite_choice(["raw/doc.pdf"], True) is True
    assert drive.resolve_overwrite_choice([], True) is False
    assert drive.resolve_overwrite_choice(["raw/doc.pdf"], False) is False
