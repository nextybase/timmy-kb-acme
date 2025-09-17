# tests/test_semantic_enrich_ctx_override.py
from __future__ import annotations

from pathlib import Path
import logging
from typing import Any, cast

import semantic.api as sapi


class DummyCtx:
    """Contesto minimale con md_dir custom per verificare l’override."""

    def __init__(self, base: Path, md: Path, raw: Path):
        self.base_dir = base
        self.md_dir = md
        self.raw_dir = raw
        self.slug = "ctx-test"


def test_enrich_frontmatter_respects_md_dir_override(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    md_custom = tmp_path / "custom_book"
    base.mkdir()
    raw.mkdir()
    md_custom.mkdir()

    # Prepara un file markdown minimale in md_custom
    md_file = md_custom / "doc_ai.md"
    md_file.write_text("Contenuto senza frontmatter", encoding="utf-8")

    ctx = DummyCtx(base=base, md=md_custom, raw=raw)
    logger = logging.getLogger("test")

    vocab = {"ai": {"aliases": {"artificial intelligence"}}}

    # cast(Any, ...) per evitare l'errore Pylance sul tipo nominale di ClientContext
    touched = sapi.enrich_frontmatter(cast(Any, ctx), logger, vocab, slug="ctx-test")

    # Deve aver arricchito il file nel md_custom, non nel path default "book"
    assert md_file in touched
    text = md_file.read_text(encoding="utf-8")
    assert "---" in text  # frontmatter presente
    assert "ai" in text or "tags:" in text
