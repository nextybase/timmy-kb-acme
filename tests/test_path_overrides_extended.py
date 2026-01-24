# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, cast

from semantic import api as sapi
from semantic import convert_service


class _Ctx:
    # Protocol minimale compatibile con semantic.api
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
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)


def test_convert_markdown_ignores_ctx_overrides(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "custom_raw"  # deve stare sotto base
    book = base / "custom_book"  # idem
    base.mkdir()
    _write_minimal_layout(base)
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    (base / "normalized" / "dummy.md").write_text("# Dummy\n", encoding="utf-8")
    ctx = _Ctx(base, raw, book)

    # 👇 RAW deve contenere almeno un PDF affinché il converter venga invocato
    (base / "raw" / "dummy.pdf").write_bytes(b"%PDF-1.4\n%dummy\n")

    # cast(Any, ...) per evitare reportArgumentType: accettiamo duck typing nei test
    mds = convert_service.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)

    assert (base / "book" / "dummy.md").exists()
    assert not (base / "custom_book" / "dummy.md").exists()
    assert any(p.name == "dummy.md" for p in mds)


def test_build_markdown_book_uses_context_base_dir_for_vocab(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)
    ctx = _Ctx(base, raw, book)

    # converter: crea almeno un md
    def _fake_convert_md(ctxlike, logger, *, slug: str) -> List[Path]:
        p = book / "B.md"
        p.write_text("# B\n", encoding="utf-8")
        # convert_markdown restituisce path relativi alla cartella book
        return [p.relative_to(book)]

    monkeypatch.setattr(sapi, "convert_markdown", _fake_convert_md, raising=True)

    # README/SUMMARY
    def _fake_write_summary(context, logger, *, slug):  # noqa: ANN001
        summary = context.book_dir / "SUMMARY.md"
        readme = context.book_dir / "README.md"
        summary.write_text("* [B](B.md)", encoding="utf-8")
        readme.write_text("# Book", encoding="utf-8")
        return summary, readme

    monkeypatch.setattr(sapi, "write_summary_and_readme", _fake_write_summary, raising=True)
    # intercetta la base_dir passata a load_reviewed_vocab
    seen_base: Dict[str, str] = {}

    def _fake_load_vocab(base_dir: Path, logger) -> Dict[str, Dict[str, set]]:
        seen_base["path"] = str(base_dir)
        # ritorna vocab non vuoto per forzare enrich_frontmatter
        return {"ai": {"aliases": {"artificial intelligence"}}}

    monkeypatch.setattr(sapi, "load_reviewed_vocab", _fake_load_vocab, raising=True)
    # enrich_frontmatter no-op che non fallisce
    monkeypatch.setattr(sapi, "enrich_frontmatter", lambda *a, **k: [], raising=True)

    out = sapi.build_markdown_book(cast(Any, ctx), _logger(), slug=ctx.slug)
    assert (book / "README.md").exists()
    assert (book / "SUMMARY.md").exists()
    assert any(p.name == "B.md" for p in out)
    # verifica che la base passata a load_reviewed_vocab sia proprio ctx.base_dir
    assert seen_base["path"] == str(base)
