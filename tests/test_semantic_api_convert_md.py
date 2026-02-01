# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_semantic_api_convert_md.py
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from semantic.context_paths import ContextPaths
from semantic.convert_service import _call_convert_md


def _ctx(
    base: Path = Path("."),
    raw: Path = Path("."),
    normalized: Path = Path("normalized"),
    md: Path = Path("book"),
) -> ContextPaths:
    return ContextPaths(
        repo_root_dir=base,
        raw_dir=raw,
        normalized_dir=normalized,
        book_dir=md,
        slug="x",
    )


def test_call_convert_md_raises_on_non_callable() -> None:
    # ora solleva ConversionError con contesto (slug/file_path), non RuntimeError
    with pytest.raises(ConversionError, match="not callable"):
        _call_convert_md(object(), _ctx(), Path("book"))


def test_call_convert_md_calls_without_book_dir() -> None:
    called = {"ok": False}

    def f(ctx):
        assert isinstance(ctx, ContextPaths)
        called["ok"] = True

    _call_convert_md(f, _ctx(), Path("book"))
    assert called["ok"] is True


def test_call_convert_md_calls_with_book_dir_kw() -> None:
    called = {"ok": False, "md": None}

    def f(ctx, *, book_dir: Path):
        assert isinstance(ctx, ContextPaths)
        called["ok"] = True
        called["md"] = book_dir

    _call_convert_md(f, _ctx(md=Path("book")), Path("book"))
    assert called["ok"] is True
    assert called["md"] == Path("book")
