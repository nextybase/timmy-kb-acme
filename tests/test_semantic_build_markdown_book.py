# tests/test_semantic_build_markdown_book.py
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

    # Prepara un md fittizio così convert_markdown/summary/readme hanno materiale
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
