# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ui.manage.drive import execute_drive_download


class _DummyStatus:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class _DummySt:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.toasts: list[str] = []
        self.errors: list[str] = []

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def toast(self, msg: str) -> None:
        self.toasts.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)


class _DummyLogger:
    def __init__(self) -> None:
        self.exceptions: list[tuple[str, dict[str, Any]]] = []

    def exception(self, message: str, *, extra: dict[str, Any]) -> None:
        self.exceptions.append((message, extra))


def _status_guard(*_: Any, **__: Any):
    status = _DummyStatus()

    @contextmanager
    def _guard() -> Iterator[_DummyStatus]:
        yield status

    return _guard()


def test_execute_drive_download_passes_require_env_true() -> None:
    st = _DummySt()
    logger = _DummyLogger()
    received: dict[str, Any] = {}

    def _download(slug: str, *, overwrite: bool, require_env: bool) -> list[Path]:
        received["slug"] = slug
        received["overwrite"] = overwrite
        received["require_env"] = require_env
        return []

    ok = execute_drive_download(
        "acme",
        [],
        download_with_progress=_download,
        download_simple=None,
        invalidate_index=None,
        logger=logger,
        st=st,
        status_guard=_status_guard,
        overwrite_requested=False,
    )

    assert ok is True
    assert received["slug"] == "acme"
    assert received["overwrite"] is False
    assert received["require_env"] is True


def test_execute_drive_download_fails_on_legacy_signature_without_require_env() -> None:
    st = _DummySt()
    logger = _DummyLogger()

    def _legacy_download(slug: str, *, overwrite: bool) -> list[Path]:
        _ = (slug, overwrite)
        return []

    ok = execute_drive_download(
        "acme",
        [],
        download_with_progress=_legacy_download,
        download_simple=None,
        invalidate_index=None,
        logger=logger,
        st=st,
        status_guard=_status_guard,
        overwrite_requested=False,
    )

    assert ok is False
    assert st.errors
    assert logger.exceptions
