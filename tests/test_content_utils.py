# tests/test_content_utils.py  (aggiunta di due test mirati)
from pathlib import Path

import pytest

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError


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
