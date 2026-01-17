# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_enrich_ctx_override.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from semantic import frontmatter_service


class DummyCtx:
    def __init__(self, base: Path, md: Path, raw: Path):
        self.base_dir = base
        self.repo_root_dir = base
        self.md_dir = md
        self.raw_dir = raw
        self.slug = "ctx-test"


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")


def test_enrich_frontmatter_ignores_md_dir_override(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    md_custom = base / "custom_book"  # sottocartella di base (safe)
    base.mkdir()
    raw.mkdir()
    md_custom.mkdir()
    _write_minimal_layout(base)

    md_file = (base / "book") / "doc_ai.md"
    md_file.write_text("---\ntitle:\n---\nContenuto senza frontmatter", encoding="utf-8")

    ctx = DummyCtx(base=base, md=md_custom, raw=raw)
    logger = logging.getLogger("test")

    vocab = {"ai": {"aliases": {"artificial intelligence"}}}
    touched = frontmatter_service.enrich_frontmatter(cast(Any, ctx), logger, vocab, slug="ctx-test")
    assert md_file in touched
    text = md_file.read_text(encoding="utf-8")
    assert "---" in text
    assert "ai" in text or "tags:" in text


def test_enrich_frontmatter_does_not_touch_md_dir_outside_base(tmp_path: Path):
    base = tmp_path / "kb"
    raw = base / "raw"
    # md_dir fratello della sandbox → deve fallire per path-safety
    md_outside = tmp_path / "custom_book"
    base.mkdir()
    raw.mkdir()
    md_outside.mkdir()
    _write_minimal_layout(base)

    outside_file = md_outside / "doc_ai.md"
    outside_file.write_text("Contenuto", encoding="utf-8")

    inside_file = (base / "book") / "doc_ai.md"
    inside_file.write_text("---\ntitle:\n---\nContenuto", encoding="utf-8")

    ctx = DummyCtx(base=base, md=md_outside, raw=raw)
    logger = logging.getLogger("test")

    touched = frontmatter_service.enrich_frontmatter(
        cast(Any, ctx), logger, {"ai": {"aliases": set()}}, slug="ctx-test"
    )
    assert inside_file in touched
    assert outside_file.read_text(encoding="utf-8") == "Contenuto"
