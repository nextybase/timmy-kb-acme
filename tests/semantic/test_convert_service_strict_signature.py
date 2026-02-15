# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from semantic.context_paths import ContextPaths
from semantic.convert_service import _call_convert_md


def _ctx(base: Path) -> ContextPaths:
    book = base / "book"
    raw = base / "raw"
    normalized = base / "normalized"
    return ContextPaths(
        repo_root_dir=base,
        raw_dir=raw,
        normalized_dir=normalized,
        book_dir=book,
        slug="strict-signature",
    )


def test_call_convert_md_accepts_strict_keyword_contract(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)
    calls: list[Path | None] = []

    def convert_fn(ctx: ContextPaths, *, book_dir: Path | None = None) -> None:
        assert isinstance(ctx, ContextPaths)
        calls.append(book_dir)

    ctx = _ctx(base)
    _call_convert_md(convert_fn, ctx, None)
    _call_convert_md(convert_fn, ctx, ctx.book_dir)

    assert calls == [None, ctx.book_dir]


def test_call_convert_md_rejects_legacy_positional_signature(tmp_path: Path) -> None:
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(base)

    def legacy_convert(ctx: ContextPaths, book_dir: Path, /) -> None:
        _ = (ctx, book_dir)

    with pytest.raises(ConversionError, match=r"required signature is legacy_convert\(ctx, book_dir=\.\.\.\)"):
        _call_convert_md(legacy_convert, ctx, ctx.book_dir)


def test_call_convert_md_raises_on_non_callable(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path / "kb")
    with pytest.raises(ConversionError, match="not callable"):
        _call_convert_md(object(), ctx, ctx.book_dir)


def test_call_convert_md_wraps_typeerror_with_context(tmp_path: Path) -> None:
    def bad_converter(a, b, c):
        return None

    base = tmp_path / "out"
    book = base / "book"
    raw = base / "raw"
    normalized = base / "normalized"
    book.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    normalized.mkdir(parents=True, exist_ok=True)

    ctx = ContextPaths(
        repo_root_dir=base,
        raw_dir=raw,
        normalized_dir=normalized,
        book_dir=book,
        slug="zzz",
    )

    with pytest.raises(ConversionError) as excinfo:
        _call_convert_md(bad_converter, ctx, book)

    err = excinfo.value
    assert "convert_md call failed" in str(err)
    assert getattr(err, "slug", None) == "zzz"
    assert Path(getattr(err, "file_path", "")) == book
