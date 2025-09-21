# tests/test_observability_smoke.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import semantic.api as sapi


@dataclass
class _Ctx:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def _logger(name: str = "test.obs") -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    return lg


def test_observability_indexing_success(monkeypatch, tmp_path, caplog):
    # Setup workspace minimo con 2 file MD
    base = tmp_path / "output" / "timmy-kb-obs"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")
    ctx = _Ctx(base_dir=base, raw_dir=base / "raw", md_dir=book, slug="obs")
    logger = _logger("test.obs.index")

    # Stub embeddings e inserimento DB
    class Emb:
        def embed_texts(
            self,
            texts: Sequence[str],
            *,
            model: str | None = None,
        ) -> Iterable[list[float]]:  # type: ignore[override]
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(sapi, "_insert_chunks", lambda **kwargs: 1)

    caplog.set_level(logging.INFO)
    _ = sapi.index_markdown_to_db(ctx, logger, slug="obs", scope="book", embeddings_client=Emb(), db_path=None)

    # Verifica record strutturati
    started = next(
        r for r in caplog.records if r.msg == "phase_started" and getattr(r, "phase", None) == "index_markdown_to_db"
    )
    completed = next(
        r for r in caplog.records if r.msg == "phase_completed" and getattr(r, "phase", None) == "index_markdown_to_db"
    )
    assert getattr(started, "status", None) == "start"
    assert getattr(completed, "status", None) == "success"
    assert isinstance(getattr(completed, "duration_ms", 0), int) and getattr(completed, "duration_ms", 0) >= 0
    # artifacts deve riflettere 2 inserimenti
    assert getattr(completed, "artifacts", None) == 2


def test_observability_build_book_success(monkeypatch, tmp_path, caplog):
    # Patch pipeline per generare rapidamente 2 MD
    base = tmp_path / "kb" / "obs"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    # RAW deve contenere almeno un PDF affinché il converter venga invocato
    (raw / "dummy.pdf").write_bytes(b"%PDF-1.4\n%dummy\n")

    def _fake_convert(ctx, md_dir: Path | None = None) -> None:  # type: ignore[no-untyped-def]
        target = md_dir or ctx.md_dir
        (target / "A.md").write_text("A", encoding="utf-8")
        (target / "B.md").write_text("B", encoding="utf-8")

    monkeypatch.setattr(sapi, "_convert_md", _fake_convert)
    monkeypatch.setattr(
        sapi, "_gen_summary", lambda ctx: (ctx.md_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")
    )
    monkeypatch.setattr(
        sapi, "_gen_readme", lambda ctx: (ctx.md_dir / "README.md").write_text("# R\n", encoding="utf-8")
    )
    # Evita enrich_frontmatter post build
    monkeypatch.setattr(sapi, "_load_reviewed_vocab", lambda base_dir, logger: {}, raising=True)

    ctx = _Ctx(base_dir=base, raw_dir=raw, md_dir=book, slug="obs")
    logger = _logger("test.obs.build")

    caplog.set_level(logging.INFO)
    _ = sapi.build_markdown_book(ctx, logger, slug="obs")

    started = next(
        r for r in caplog.records if r.msg == "phase_started" and getattr(r, "phase", None) == "build_markdown_book"
    )
    completed = next(
        r for r in caplog.records if r.msg == "phase_completed" and getattr(r, "phase", None) == "build_markdown_book"
    )
    assert getattr(started, "status", None) == "start"
    assert getattr(completed, "status", None) == "success"
    assert isinstance(getattr(completed, "duration_ms", 0), int) and getattr(completed, "duration_ms", 0) >= 0
    assert getattr(completed, "artifacts", None) == 2


def test_observability_indexing_failure_emits_error(monkeypatch, tmp_path, caplog):
    base = tmp_path / "output" / "timmy-kb-obs"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    ctx = _Ctx(base_dir=base, raw_dir=base / "raw", md_dir=book, slug="obs")
    logger = _logger("test.obs.index.fail")

    class Emb:
        def embed_texts(
            self,
            texts: Sequence[str],
            *,
            model: str | None = None,
        ) -> Iterable[list[float]]:  # type: ignore[override]
            return [[1.0, 0.0] for _ in texts]

    def _boom(**kwargs: Any) -> int:  # type: ignore[no-untyped-def]
        raise RuntimeError("db boom")

    monkeypatch.setattr(sapi, "_insert_chunks", _boom)

    caplog.set_level(logging.INFO)
    import pytest

    with pytest.raises(RuntimeError):
        sapi.index_markdown_to_db(ctx, logger, slug="obs", scope="book", embeddings_client=Emb(), db_path=None)

    failed = next(
        r for r in caplog.records if r.msg == "phase_failed" and getattr(r, "phase", None) == "index_markdown_to_db"
    )
    assert getattr(failed, "status", None) == "failed"
    assert "db boom" in str(getattr(failed, "error", ""))
