# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from ui.utils import docs_view


def test_load_markdown_reads_file(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    doc_path = repo / "docs" / "sample.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("# Hello\n", encoding="utf-8")

    monkeypatch.setattr(docs_view, "get_repo_root", lambda: repo)

    content = docs_view.load_markdown(doc_path)

    assert "# Hello" in content


def test_load_markdown_blocks_outside_repo(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    outside_path = tmp_path / "outside.md"
    outside_path.write_text("boom", encoding="utf-8")

    monkeypatch.setattr(docs_view, "get_repo_root", lambda: repo)

    content = docs_view.load_markdown(outside_path)

    assert "impossibile leggere" in content
    assert "outside.md" in content
