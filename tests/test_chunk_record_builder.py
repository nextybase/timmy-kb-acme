# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.content_utils import build_chunk_records_from_markdown_files
from pipeline.exceptions import ConfigError


def test_build_chunk_records_from_markdown_files(tmp_path: Path) -> None:
    slug = "dummy"
    file_one = tmp_path / "one.md"
    file_one.write_text("---\ntitle: One\n---\nPrimo chunk", encoding="utf-8")
    file_two = tmp_path / "two.md"
    file_two.write_text("---\ntitle: Two\n---\nSecondo chunk", encoding="utf-8")

    records = build_chunk_records_from_markdown_files(slug, [file_one, file_two], perimeter_root=tmp_path)
    assert len(records) == 2
    first, second = records

    assert first["chunk_index"] == 0
    assert first["slug"] == slug
    assert first["source_path"] == "one.md"
    assert first["text"] == "Primo chunk"
    assert isinstance(first["metadata"], dict)

    another_run = build_chunk_records_from_markdown_files(slug, [file_one, file_two], perimeter_root=tmp_path)
    assert first["id"] == another_run[0]["id"]
    assert first["created_at"] == second["created_at"]


def test_build_chunk_records_heading_chunking(tmp_path: Path) -> None:
    slug = "dummy"
    md_file = tmp_path / "book.md"
    md_file.write_text("---\ntitle: Book\n---\n# Intro\nBenvenuto\n# Details\nDettagli", encoding="utf-8")

    records = build_chunk_records_from_markdown_files(slug, [md_file], chunking="heading", perimeter_root=tmp_path)
    assert len(records) == 2
    first, second = records

    assert first["chunk_index"] == 0
    assert second["chunk_index"] == 1
    assert first["metadata"].get("layout_section") == "Intro"
    assert second["metadata"].get("layout_section") == "Details"
    assert first["id"] != second["id"]

    repeat = build_chunk_records_from_markdown_files(slug, [md_file], chunking="heading", perimeter_root=tmp_path)
    assert first["id"] == repeat[0]["id"]
    assert second["id"] == repeat[1]["id"]


def test_build_chunk_records_rejects_paths_outside_base(tmp_path: Path) -> None:
    slug = "dummy"
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("Fuori", encoding="utf-8")

    with pytest.raises(ConfigError, match="outside perimeter_root"):
        build_chunk_records_from_markdown_files(slug, [outside], perimeter_root=base_dir)


def test_build_chunk_records_accepts_paths_inside_base(tmp_path: Path) -> None:
    slug = "dummy"
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    inside = base_dir / "inside.md"
    inside.write_text("---\ntitle: Dentro\n---\nDentro", encoding="utf-8")

    records = build_chunk_records_from_markdown_files(slug, [inside], perimeter_root=base_dir)
    assert len(records) == 1
    assert records[0]["source_path"] == "inside.md"


def test_build_chunk_records_requires_perimeter_root(tmp_path: Path) -> None:
    md_file = tmp_path / "doc.md"
    md_file.write_text("Contenuto", encoding="utf-8")

    with pytest.raises(ConfigError, match="perimeter_root is required"):
        build_chunk_records_from_markdown_files("dummy", [md_file])
