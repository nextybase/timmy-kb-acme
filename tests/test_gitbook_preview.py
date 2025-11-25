# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline.gitbook_preview import _log_layout_summary


def test_log_layout_summary_records_entries(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    summary = book_dir / "layout_summary.md"
    summary.write_text("- **strategy**: descrizione\n- **data**: descrizione", encoding="utf-8")

    caplog.set_level("INFO")
    _log_layout_summary(book_dir, slug="acme", redact_logs=False)

    assert any("Layout summary disponibile" in rec.message for rec in caplog.records)
    info_records = [rec for rec in caplog.records if "Layout summary disponibile" in rec.message]
    assert info_records
    assert len(info_records[0].entries) == 2
    assert info_records[0].entries == ["strategy", "data"]


def test_log_layout_summary_warns_when_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()

    caplog.set_level("INFO")
    _log_layout_summary(book_dir, slug="acme", redact_logs=False)

    assert any("layout_summary.md non è presente" in rec.message for rec in caplog.records)
