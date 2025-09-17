# tests/test_semantic_enrich_ctx_override.py
from __future__ import annotations

from pathlib import Path
import logging
from typing import Any, cast

import pytest
import semantic.api as sapi


class DummyCtx:
    def __init__(self, base: Path, md: Path, raw: Path):
        self.base_dir = base
        self.md_dir = md
        self.raw_dir = raw
        self.slug = "ctx-test"


def test_enrich_frontmatter_respects_md_dir_override(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    md_custom = base / "custom_book"  # sottocartella di base (safe)
    base.mkdir()
    raw.mkdir()
    md_custom.mkdir()

    md_file = md_custom / "doc_ai.md"
    md_file.write_text("Contenuto senza frontmatter", encoding="utf-8")

    ctx = DummyCtx(base=base, md=md_custom, raw=raw)
    logger = logging.getLogger("test")

    vocab = {"ai": {"aliases": {"artificial intelligence"}}}
    touched = sapi.enrich_frontmatter(cast(Any, ctx), logger, vocab, slug="ctx-test")
    assert md_file in touched
    text = md_file.read_text(encoding="utf-8")
    assert "---" in text
    assert "ai" in text or "tags:" in text


def test_enrich_frontmatter_rejects_md_dir_outside_base(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    # md_dir fratello della sandbox → deve fallire per path-safety
    md_outside = tmp_path / "custom_book"
    base.mkdir()
    raw.mkdir()
    md_outside.mkdir()

    md_file = md_outside / "doc_ai.md"
    md_file.write_text("Contenuto", encoding="utf-8")

    ctx = DummyCtx(base=base, md=md_outside, raw=raw)
    logger = logging.getLogger("test")

    # L'eccezione specifica dipende dall'implementazione di ensure_within;
    # lasciamo intentionally generico per compat.
    with pytest.raises(Exception):
        sapi.enrich_frontmatter(cast(Any, ctx), logger, {"ai": {"aliases": set()}}, slug="ctx-test")
