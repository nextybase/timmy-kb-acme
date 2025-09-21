# tests/test_semantic_api_errors.py
from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from semantic.api import _call_convert_md, _CtxShim  # test su funzione interna by design


def test_call_convert_md_wraps_typeerror_with_context(tmp_path: Path):
    def bad_converter(a, b, c):
        return None

    base = tmp_path / "out"
    book = base / "book"
    raw = base / "raw"
    book.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)

    ctx = _CtxShim(base_dir=base, raw_dir=raw, md_dir=book, slug="zzz")

    with pytest.raises(ConversionError) as ei:
        _call_convert_md(bad_converter, ctx, book)

    err = ei.value
    assert "convert_md call failed" in str(err)
    assert getattr(err, "slug", None) == "zzz"
    assert Path(getattr(err, "file_path", "")) == book
