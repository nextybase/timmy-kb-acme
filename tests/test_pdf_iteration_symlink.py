from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError, ConversionError
from semantic import api as sapi
from semantic.auto_tagger import extract_semantic_candidates
from semantic.config import SemanticConfig
from tests.utils.symlink import make_symlink


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def test_auto_tagger_skips_symlink_outside_base(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    outside = tmp_path / "outside"
    raw.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)

    target_pdf = outside / "evil.pdf"
    target_pdf.write_bytes(b"%PDF-1.4\n%\n")

    link = raw / "link.pdf"
    make_symlink(target_pdf, link)

    cfg = SemanticConfig(base_dir=str(base))
    cands = extract_semantic_candidates(raw, cfg)
    assert cands == {}


def test_convert_markdown_treats_only_symlinks_as_no_pdfs(tmp_path: Path):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    raw = ctx.raw_dir
    book = ctx.md_dir
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    outside = tmp_path / "outside2"
    outside.mkdir(parents=True, exist_ok=True)
    target_pdf = outside / "evil2.pdf"
    target_pdf.write_bytes(b"%PDF-1.4\n%\n")
    link = raw / "evil2.pdf"
    make_symlink(target_pdf, link)

    with pytest.raises(ConfigError) as ei:
        sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)
    err = ei.value
    assert Path(getattr(err, "file_path", "")) == raw


def test_convert_markdown_raises_when_only_readme_summary_with_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "kb"
    ctx = _Ctx(base)
    logger = _NoopLogger()

    # RAW con vero PDF
    ctx.raw_dir.mkdir(parents=True, exist_ok=True)
    (ctx.raw_dir / "doc.pdf").write_bytes(b"%PDF-1.4\n%\n")
    # BOOK con soli README/SUMMARY
    ctx.md_dir.mkdir(parents=True, exist_ok=True)
    (ctx.md_dir / "README.md").write_text("# R\n", encoding="utf-8")
    (ctx.md_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    # Falsifica converter a no-op
    monkeypatch.setattr(sapi, "_call_convert_md", lambda *a, **k: None)

    with pytest.raises(ConversionError):
        sapi.convert_markdown(ctx, logger=logger, slug=ctx.slug)
