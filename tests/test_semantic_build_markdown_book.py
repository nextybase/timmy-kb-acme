# tests/test_semantic_build_markdown_book.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import semantic.api as sapi


@dataclass
class C:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def _ctx(base: Path) -> C:
    return C(
        base_dir=base,
        raw_dir=base / "raw",
        md_dir=base / "book",
        slug="e2e",
    )


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_build_markdown_book_end_to_end(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    # Confinare i percorsi sotto tmp_path
    monkeypatch.setattr(
        sapi,
        "get_paths",
        lambda slug: {
            "base": base,
            "raw": raw,
            "book": book,
            "semantic": base / "semantic",
        },
    )

    # Simula la conversione: crea 2 markdown "A.md" e "B.md" in book/
    def _fake_convert(ctx, md_dir: Path | None = None) -> None:
        target = md_dir or ctx.md_dir
        _write(target / "A.md", "Body A\n")
        _write(target / "B.md", "Body B\n")

    # Genera README/SUMMARY minimi
    monkeypatch.setattr(sapi, "_convert_md", _fake_convert)
    monkeypatch.setattr(sapi, "_gen_summary", lambda ctx: _write(ctx.md_dir / "SUMMARY.md", "# Summary\n"))
    monkeypatch.setattr(sapi, "_gen_readme", lambda ctx: _write(ctx.md_dir / "README.md", "# Readme\n"))
    monkeypatch.setattr(sapi, "_validate_md", lambda ctx: None)

    # Vocabolario non vuoto per attivare enrich_frontmatter
    monkeypatch.setattr(
        sapi,
        "_load_reviewed_vocab",
        lambda base_dir, logger: {"analytics": {"aliases": {"analytics"}}},
    )

    ctx = _ctx(base)
    logger = logging.getLogger("test")

    # cast(Any, …): bypass del nominal type (ClientContext) mantenendo la logica invariata
    mds = sapi.build_markdown_book(cast(Any, ctx), logger, slug="e2e")

    names = {p.name for p in mds}
    assert {"A.md", "B.md"}.issubset(names)
    assert (book / "SUMMARY.md").exists() and (book / "README.md").exists()
