from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, cast

import semantic.api as sem


class _Ctx:
    # Protocol minimale compatibile con semantic.api
    def __init__(self, base: Path, raw: Path, md: Path, slug: str = "x"):
        self.base_dir = base
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


def test_convert_markdown_respects_ctx_overrides(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "custom_raw"  # deve stare sotto base
    book = base / "custom_book"  # idem
    base.mkdir()
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    ctx = _Ctx(base, raw, book)

    # 👇 RAW deve contenere almeno un PDF affinché il converter venga invocato
    (raw / "dummy.pdf").write_bytes(b"%PDF-1.4\n%dummy\n")

    # Fake converter: deve scrivere in md_dir
    def _fake_convert_md(ctxlike, md_dir: Path):
        (md_dir / "A.md").write_text("# A\n", encoding="utf-8")

    monkeypatch.setattr(sem, "_convert_md", _fake_convert_md, raising=True)

    # Falsifica i generatori README/SUMMARY per non fare I/O complesso
    def _fake_summary(shim):
        (shim.md_dir / "SUMMARY.md").write_text("* [A](A.md)", "utf-8")

    def _fake_readme(shim):
        (shim.md_dir / "README.md").write_text("# Book", "utf-8")

    monkeypatch.setattr(sem, "_gen_summary", _fake_summary, raising=True)
    monkeypatch.setattr(sem, "_gen_readme", _fake_readme, raising=True)
    monkeypatch.setattr(sem, "_validate_md", lambda shim: None, raising=True)

    # cast(Any, ...) per evitare reportArgumentType: accettiamo duck typing nei test
    mds = sem.convert_markdown(cast(Any, ctx), _logger(), slug=ctx.slug)

    assert (book / "A.md").exists()
    assert any(p.name == "A.md" for p in mds)


def test_build_markdown_book_uses_context_base_dir_for_vocab(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    raw = base / "raw"
    book = base / "book"
    for d in (base, raw, book):
        d.mkdir(parents=True, exist_ok=True)
    ctx = _Ctx(base, raw, book)

    # converter: crea almeno un md
    def _fake_convert_md(ctxlike, logger, *, slug: str) -> List[Path]:
        p = book / "B.md"
        p.write_text("# B\n", encoding="utf-8")
        # convert_markdown restituisce path relativi alla cartella book
        return [p.relative_to(book)]

    monkeypatch.setattr(sem, "convert_markdown", _fake_convert_md, raising=True)

    # README/SUMMARY
    monkeypatch.setattr(
        sem,
        "_gen_summary",
        lambda shim: (shim.md_dir / "SUMMARY.md").write_text("* [B](B.md)", "utf-8"),
        raising=True,
    )
    monkeypatch.setattr(
        sem,
        "_gen_readme",
        lambda shim: (shim.md_dir / "README.md").write_text("# Book", "utf-8"),
        raising=True,
    )
    monkeypatch.setattr(sem, "_validate_md", lambda shim: None, raising=True)

    # intercetta la base_dir passata a load_reviewed_vocab
    seen_base: Dict[str, str] = {}

    def _fake_load_vocab(base_dir: Path, logger) -> Dict[str, Dict[str, set]]:
        seen_base["path"] = str(base_dir)
        # ritorna vocab non vuoto per forzare enrich_frontmatter
        return {"ai": {"aliases": {"artificial intelligence"}}}

    monkeypatch.setattr(sem, "load_reviewed_vocab", _fake_load_vocab, raising=True)
    # enrich_frontmatter no-op che non fallisce
    monkeypatch.setattr(sem, "enrich_frontmatter", lambda *a, **k: [], raising=True)

    out = sem.build_markdown_book(cast(Any, ctx), _logger(), slug=ctx.slug)
    assert (book / "README.md").exists()
    assert (book / "SUMMARY.md").exists()
    assert any(p.name == "B.md" for p in out)
    # verifica che la base passata a load_reviewed_vocab sia proprio ctx.base_dir
    assert seen_base["path"] == str(base)
