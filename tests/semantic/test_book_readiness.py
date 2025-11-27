# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from semantic.book_readiness import check_book_dir, is_book_ready


def test_check_book_dir_missing(tmp_path: Path) -> None:
    configured = tmp_path / "book"
    ready, errors = check_book_dir(configured)
    assert not ready
    assert any("Directory inesistente" in err for err in errors)


def test_book_dir_needs_content(tmp_path: Path) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "README.md").write_text("# Title", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("## Summary", encoding="utf-8")

    ready, errors = check_book_dir(book_dir)
    assert not ready
    assert any("Nessun file Markdown di contenuto" in err for err in errors)
    assert not is_book_ready(book_dir)


def test_book_dir_ready(tmp_path: Path) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "README.md").write_text("# Title", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("## Summary", encoding="utf-8")
    (book_dir / "chapter1.md").write_text("Content", encoding="utf-8")

    ready, errors = check_book_dir(book_dir)
    assert ready
    assert errors == []
    assert is_book_ready(book_dir)


@pytest.mark.parametrize(
    "setup, missing_label",
    [
        (lambda dir: dir / "README.md", "README"),
        (lambda dir: dir / "SUMMARY.md", "SUMMARY"),
    ],
)
def test_book_dir_missing_readme_or_summary(tmp_path: Path, setup, missing_label: str) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "README.md").write_text("# Title", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("## Summary", encoding="utf-8")
    missing = setup(book_dir)
    if missing.exists():
        missing.unlink()
    ready, errors = check_book_dir(book_dir)
    assert not ready
    assert any(missing_label in err for err in errors)
    assert not is_book_ready(book_dir)


def test_nested_markdown_counts_as_content(tmp_path: Path) -> None:
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "README.md").write_text("# Title", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("## Summary", encoding="utf-8")
    sub_dir = book_dir / "area"
    sub_dir.mkdir()
    (sub_dir / "intro.md").write_text("Nested content", encoding="utf-8")
    ready, errors = check_book_dir(book_dir)
    assert ready
    assert errors == []
    assert is_book_ready(book_dir)
