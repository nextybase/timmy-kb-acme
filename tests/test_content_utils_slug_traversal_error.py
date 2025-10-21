from pathlib import Path
from types import SimpleNamespace

import pytest

import timmykb.pipeline.content_utils as cu
from pipeline.exceptions import PipelineError


def test_validate_markdown_dir_traversal_includes_slug(tmp_path: Path):
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)
    # md_dir fuori dal perimetro base -> path-safety deve fallire
    outside = tmp_path / "outside_book"
    outside.mkdir(parents=True, exist_ok=True)

    ctx = SimpleNamespace(base_dir=base, md_dir=outside, slug="dummy")

    with pytest.raises(PipelineError) as exc:
        cu.validate_markdown_dir(ctx, md_dir=outside)

    # Il messaggio deve contenere lo slug per diagnostica
    assert "slug=dummy" in str(exc.value)
