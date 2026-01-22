# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.content_utils import build_chunk_records_from_markdown_files
from pipeline.exceptions import PipelineError


def test_build_chunk_records_from_markdown_files(tmp_path: Path) -> None:
    slug = "dummy"
    file_one = tmp_path / "one.md"
    file_one.write_text("Primo chunk")
    file_two = tmp_path / "two.md"
    file_two.write_text("Secondo chunk")

    records = build_chunk_records_from_markdown_files(slug, [file_one, file_two])
    assert len(records) == 2
    first, second = records

    assert first["chunk_index"] == 0
    assert first["slug"] == slug
    assert first["source_path"] == str(file_one)
    assert first["text"] == "Primo chunk"
    assert isinstance(first["metadata"], dict)

    another_run = build_chunk_records_from_markdown_files(slug, [file_one, file_two])
    assert first["id"] == another_run[0]["id"]
    assert first["created_at"] == second["created_at"]


def test_build_chunk_records_heading_chunking(tmp_path: Path) -> None:
    slug = "dummy"
    md_file = tmp_path / "book.md"
    md_file.write_text("# Intro\nBenvenuto\n# Details\nDettagli", encoding="utf-8")

    records = build_chunk_records_from_markdown_files(slug, [md_file], chunking="heading")
    assert len(records) == 2
    first, second = records

    assert first["chunk_index"] == 0
    assert second["chunk_index"] == 1
    assert first["metadata"].get("layout_section") == "Intro"
    assert second["metadata"].get("layout_section") == "Details"
    assert first["id"] != second["id"]

    repeat = build_chunk_records_from_markdown_files(slug, [md_file], chunking="heading")
    assert first["id"] == repeat[0]["id"]
    assert second["id"] == repeat[1]["id"]


def test_build_chunk_records_rejects_paths_outside_base(tmp_path: Path) -> None:
    slug = "dummy"
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Fuori", encoding="utf-8")

    with pytest.raises(PipelineError, match="Markdown path fuori perimetro"):
        build_chunk_records_from_markdown_files(slug, [outside], perimeter_root=base_dir)


def test_build_chunk_records_accepts_paths_inside_base(tmp_path: Path) -> None:
    slug = "dummy"
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    inside = base_dir / "inside.md"
    inside.write_text("Dentro", encoding="utf-8")

    records = build_chunk_records_from_markdown_files(slug, [inside], perimeter_root=base_dir)
    assert len(records) == 1
    assert records[0]["source_path"] == "inside.md"
