# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_build_markdown_book.py
import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConversionError
from semantic import api as sapi


class _Ctx:
    def __init__(self, base: Path, slug: str = "obs"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


def test_build_markdown_book_no_success_if_enrich_fails(tmp_path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    # Prepara un md fittizio cosi convert_markdown/summary/readme hanno materiale
    (book / "alpha.md").write_text("# A\n\n", encoding="utf-8")

    # Monkeypatch: vocabolario presente e enrich che fallisce
    monkeypatch.setattr(sapi, "load_reviewed_vocab", lambda base_dir, logger: {"canon": {"aliases": set()}})

    def _boom(*args, **kwargs):
        raise ConversionError("boom", slug="obs", file_path=book)

    monkeypatch.setattr(sapi, "enrich_frontmatter", _boom)

    ctx = _Ctx(base)

    caplog.clear()
    with pytest.raises(ConversionError):
        sapi.build_markdown_book(ctx, logger=_NoopLogger(), slug="obs")

    # Nessuna evidenza di "success" della fase build_markdown_book nei log
    success_records = [
        r
        for r in caplog.records
        if "build_markdown_book" in (getattr(r, "message", "") or "") and "success" in r.message.lower()
    ]
    assert not success_records


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def test_build_markdown_book_logs_enriched_count(tmp_path, caplog, monkeypatch):
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)

    ctx = _Ctx(base)

    monkeypatch.setattr(sapi, "convert_markdown", lambda *_, **__: [base / "book" / "a.md", base / "book" / "b.md"])
    monkeypatch.setattr(sapi, "_require_reviewed_vocab", lambda *_, **__: {"canon": {"aliases": set()}})
    monkeypatch.setattr(sapi, "enrich_frontmatter", lambda *_, **__: [base / "book" / "a.md"])
    monkeypatch.setattr(sapi, "write_summary_and_readme", lambda *_, **__: None)

    logger = logging.getLogger("semantic.book.test")
    caplog.set_level(logging.INFO, logger="semantic.book.test")

    sapi.build_markdown_book(ctx, logger=logger, slug="obs")

    assert any(
        r.getMessage() == "semantic.book.frontmatter" and getattr(r, "enriched", None) == 1 for r in caplog.records
    )


def test_run_build_workflow_clears_frontmatter_cache(monkeypatch, tmp_path):
    base = tmp_path / "kb"
    base.mkdir(parents=True, exist_ok=True)

    ctx = _Ctx(base)
    logger = logging.getLogger("semantic.book.test")

    clear_calls: list[Path | None] = []
    monkeypatch.setattr("pipeline.content_utils.clear_frontmatter_cache", lambda path=None: clear_calls.append(path))

    def _convert(*_, **__):
        return [base / "book" / "a.md"]

    def _vocab(*_, **__):
        return {"canon": {"aliases": set()}}

    def _enrich(*_, **__):
        return []

    sapi._run_build_workflow(  # type: ignore[attr-defined]
        ctx,
        logger,
        slug="obs",
        convert_fn=_convert,
        vocab_fn=_vocab,
        enrich_fn=_enrich,
        summary_fn=lambda *_, **__: None,
    )

    assert clear_calls == [None]
