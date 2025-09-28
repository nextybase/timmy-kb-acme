# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_semantic_api_list_content_markdown.py
from pathlib import Path

from src.semantic.api import list_content_markdown


def test_list_content_markdown_excludes_readme_summary(tmp_path: Path) -> None:
    book = tmp_path / "book"
    book.mkdir()
    (book / "README.md").write_text("# r\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# s\n", encoding="utf-8")
    (book / "cat.md").write_text("# c\n", encoding="utf-8")

    files = list_content_markdown(book)
    assert [p.name for p in files] == ["cat.md"]
