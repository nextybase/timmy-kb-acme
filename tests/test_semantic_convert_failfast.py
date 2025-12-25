# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import pytest

import semantic.api as sem
from pipeline.exceptions import ConfigError, ConversionError
from semantic import convert_service


class _Ctx:
    def __init__(self, base: Path, raw: Path, md: Path, slug: str = "x"):
        self.base_dir = base
        self.repo_root_dir = base
        self.raw_dir = raw
        self.md_dir = md
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
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")


def test_convert_markdown_raises_when_only_readme_summary_and_pdfs_present(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    # Presenza di almeno un PDF in RAW
    (raw / "cat").mkdir(parents=True, exist_ok=True)
    (raw / "cat" / "doc.pdf").write_bytes(b"%PDF-1.4\n%Fake\n")

    ctx = _Ctx(base, raw, book)

    # Converter che scrive solo README/SUMMARY (nessun contenuto)
    def _fake_convert_md(ctxlike, md_dir: Path):
        (md_dir / "README.md").write_text("# R\n", encoding="utf-8")
        (md_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    monkeypatch.setattr(convert_service, "_convert_md", _fake_convert_md, raising=True)

    with pytest.raises(ConversionError):
        sem.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)


def test_convert_markdown_raises_configerror_when_no_pdfs_and_only_readme_summary(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    ctx = _Ctx(base, raw, book)

    def _fake_convert_md(ctxlike, md_dir: Path):
        (md_dir / "README.md").write_text("# R\n", encoding="utf-8")
        (md_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    monkeypatch.setattr(convert_service, "_convert_md", _fake_convert_md, raising=True)

    with pytest.raises(ConfigError):
        sem.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)
