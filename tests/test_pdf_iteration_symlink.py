# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import convert_service
from semantic.auto_tagger import extract_semantic_candidates
from semantic.config import SemanticConfig
from tests._helpers.noop_logger import NoopLogger
from tests.utils.symlink import make_symlink


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.repo_root_dir = base
        self.raw_dir = base / "raw"
        self.book_dir = base / "book"
        self.slug = slug


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)


def test_auto_tagger_skips_symlink_outside_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    _write_minimal_layout(base)
    raw = base / "raw"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TAGS_NLP_BACKEND", "spacy")

    target_pdf = outside / "evil.pdf"
    target_pdf.write_bytes(b"%PDF-1.4\n%\n")

    link = raw / "link.pdf"
    make_symlink(target_pdf, link)

    cfg = SemanticConfig(repo_root_dir=base, slug="proj")
    cands = extract_semantic_candidates(raw, cfg)
    assert cands == {}


def test_convert_markdown_treats_only_symlinks_as_no_pdfs(tmp_path: Path):
    base = tmp_path / "kb"
    _write_minimal_layout(base)
    ctx = _Ctx(base)
    logger = NoopLogger()

    normalized = base / "normalized"
    book = ctx.book_dir
    normalized.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    outside = tmp_path / "outside2"
    outside.mkdir(parents=True, exist_ok=True)
    target_pdf = outside / "evil2.pdf"
    target_pdf.write_bytes(b"%PDF-1.4\n%\n")
    link = normalized / "evil2.md"
    make_symlink(target_pdf, link)

    with pytest.raises(ConfigError) as ei:
        convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    err = ei.value
    assert Path(getattr(err, "file_path", "")) == normalized


def test_convert_markdown_raises_when_only_readme_summary_with_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    _write_minimal_layout(base)
    ctx = _Ctx(base)
    logger = NoopLogger()

    # BOOK con soli README/SUMMARY
    ctx.book_dir.mkdir(parents=True, exist_ok=True)
    (ctx.book_dir / "README.md").write_text("# R\n", encoding="utf-8")
    (ctx.book_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        convert_service.convert_markdown(ctx, logger=logger, slug=ctx.slug)
