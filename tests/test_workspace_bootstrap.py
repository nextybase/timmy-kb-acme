# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline import workspace_bootstrap as wb
from pipeline.exceptions import ConfigError


def _write_custom_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("CUSTOM", encoding="utf-8")


def test_book_guard_strict_blocks_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "book" / "README.md"
    _write_custom_file(path)
    monkeypatch.setattr(wb, "is_beta_strict", lambda: True, raising=False)

    with pytest.raises(ConfigError) as excinfo:
        wb._write_book_file_guarded(path, wb.BOOK_README_TEMPLATE)
    assert excinfo.value.code == "bootstrap.book.overwrite_forbidden"


def test_book_guard_non_strict_skips_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "book" / "README.md"
    _write_custom_file(path)
    monkeypatch.setattr(wb, "is_beta_strict", lambda: False, raising=False)
    caplog.set_level(logging.WARNING, logger=wb.LOGGER.name)

    wb._write_book_file_guarded(path, wb.BOOK_README_TEMPLATE)

    assert path.read_text(encoding="utf-8") == "CUSTOM"
    assert any(
        rec.message == "workspace_bootstrap.book_skip_existing" and getattr(rec, "service_only", None) is True
        for rec in caplog.records
    )


def test_book_guard_creates_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "book" / "SUMMARY.md"
    wb._write_book_file_guarded(path, wb.BOOK_SUMMARY_TEMPLATE)
    assert path.exists()
    assert wb.BOOK_PLACEHOLDER_MARKER in path.read_text(encoding="utf-8")
