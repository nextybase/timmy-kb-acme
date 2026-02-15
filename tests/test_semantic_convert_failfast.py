# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import pytest

from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from semantic import convert_service


class _Ctx:
    def __init__(self, base: Path, raw: Path, md: Path, slug: str = "x"):
        self.base_dir = base
        self.repo_root_dir = base
        self.raw_dir = raw
        self.book_dir = md
        self.slug = slug


def _logger() -> logging.Logger:
    log = logging.getLogger("test")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}\n", encoding="utf-8")
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")


def test_convert_markdown_raises_when_normalized_markdown_is_empty(tmp_path: Path):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    safe_write_text(base / "normalized" / "empty.md", "\n", encoding="utf-8", atomic=True)

    ctx = _Ctx(base, raw, book)

    with pytest.raises(ConversionError):
        convert_service.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)


def test_convert_markdown_raises_configerror_when_only_readme_summary(tmp_path: Path):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    ctx = _Ctx(base, raw, book)

    with pytest.raises(ConfigError):
        convert_service.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)
