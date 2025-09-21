# tests/test_content_utils.py  (aggiunta di due test mirati)
from pathlib import Path

import pytest

from pipeline import content_utils as cu
from pipeline.exceptions import PipelineError


class _Ctx:
    def __init__(self, base: Path, slug: str = "ctx-slug"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


def test_validate_markdown_dir_missing_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="ctx-slug")
    # md_dir mancante
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=tmp_path / "book-missing")
    err = ei.value
    assert getattr(err, "slug", None) == "ctx-slug"
    assert Path(getattr(err, "file_path", "")) == (tmp_path / "book-missing")


def test_validate_markdown_dir_not_directory_has_slug_and_file_path(tmp_path: Path):
    ctx = _Ctx(tmp_path, slug="ctx-slug")
    file_path = tmp_path / "book-file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(PipelineError) as ei:
        cu.validate_markdown_dir(ctx, md_dir=file_path)
    err = ei.value
    assert getattr(err, "slug", None) == "ctx-slug"
    assert Path(getattr(err, "file_path", "")) == file_path
