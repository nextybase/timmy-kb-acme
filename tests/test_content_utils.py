# SPDX-License-Identifier: GPL-3.0-only
# tests/test_content_utils.py  (aggiunta di due test mirati)
from pathlib import Path
from typing import Any

import pytest

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError
from pipeline.frontmatter_utils import read_frontmatter
from semantic.config import SemanticConfig


class _Ctx:
    def __init__(self, base: Path, slug: str = "dummy"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


def test_validate_markdown_dir_missing_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="dummy")
    # md_dir mancante
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=tmp_path / "book-missing")
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert Path(getattr(err, "file_path", "")) == (tmp_path / "book-missing")


def test_validate_markdown_dir_not_directory_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="dummy")
    file_path = tmp_path / "book-file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=file_path)
    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert Path(getattr(err, "file_path", "")) == file_path


def test_validate_markdown_dir_traversal_includes_slug_in_message(tmp_path: Path):
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside_book"
    outside.mkdir(parents=True, exist_ok=True)

    ctx = _Ctx(base, slug="dummy")
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=outside)

    err = ei.value
    assert getattr(err, "slug", None) == "dummy"
    assert "slug=dummy" in str(err)


def test_write_markdown_for_pdf_preserves_created_at(tmp_path: Path, monkeypatch: Any):
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    pdf_path = raw_root / "documento.pdf"
    pdf_path.write_text("dummy", encoding="utf-8")

    target_root = tmp_path / "book"
    cfg = SemanticConfig(
        base_dir=tmp_path,
        semantic_dir=tmp_path / "semantic",
        raw_dir=raw_root,
    )

    rel_pdf = pdf_path.relative_to(raw_root).as_posix()
    candidates = {rel_pdf: {"tags": ["inaugurazione", "vision"]}}

    first_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg)
    meta_before, body_before = read_frontmatter(target_root, first_md)
    created_before = meta_before["created_at"]

    def _fail_write(*_args, **_kwargs) -> None:
        raise AssertionError("safe_write_text should not be called for idempotent Markdown")

    monkeypatch.setattr(cu, "safe_write_text", _fail_write)
    second_md = cu._write_markdown_for_pdf(pdf_path, raw_root, target_root, candidates, cfg)

    assert second_md == first_md
    meta_after, body_after = read_frontmatter(target_root, second_md, use_cache=False)
    assert meta_after["created_at"] == created_before
    assert body_after == body_before
