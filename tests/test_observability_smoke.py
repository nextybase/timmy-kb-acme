# SPDX-License-Identifier: GPL-3.0-only
# tests/test_observability_smoke.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import semantic.api as sapi
import semantic.convert_service as conv
import semantic.embedding_service as semb
import semantic.frontmatter_service as front


@dataclass
class _Ctx:
    base_dir: Path
    repo_root_dir: Path
    raw_dir: Path
    book_dir: Path
    slug: str


def _logger(name: str = "test.obs") -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    return lg


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)


def test_observability_indexing_success(monkeypatch, tmp_path, caplog):
    # Setup workspace minimo con 2 file MD
    base = tmp_path / "output" / "timmy-kb-dummy"
    _write_minimal_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")
    ctx = _Ctx(base_dir=base, repo_root_dir=base, raw_dir=base / "raw", book_dir=book, slug="dummy")
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

    monkeypatch.setattr(semb, "_insert_chunks", lambda **kwargs: 1)

    caplog.set_level(logging.INFO)
    _ = sapi.index_markdown_to_db(ctx, logger, slug="dummy", scope="book", embeddings_client=Emb(), db_path=None)

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
    base = tmp_path / "output" / "timmy-kb-dummy"
    _write_minimal_layout(base)
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

    # RAW deve contenere almeno un PDF affinché il converter venga invocato
    (raw / "dummy.pdf").write_bytes(b"%PDF-1.4\n%dummy\n")

    def _fake_convert(ctx, book_dir: Path | None = None) -> None:  # type: ignore[no-untyped-def]
        target = book_dir or ctx.book_dir
        (target / "A.md").write_text("---\ntitle: A\n---\nA", encoding="utf-8")
        (target / "B.md").write_text("---\ntitle: B\n---\nB", encoding="utf-8")

    monkeypatch.setattr(conv, "_convert_md", _fake_convert)
    monkeypatch.setattr(
        front, "_gen_summary", lambda ctx: (ctx.book_dir / "SUMMARY.md").write_text("# S\n", encoding="utf-8")
    )
    monkeypatch.setattr(
        front, "_gen_readme", lambda ctx: (ctx.book_dir / "README.md").write_text("# R\n", encoding="utf-8")
    )
    monkeypatch.setattr(
        sapi,
        "_require_reviewed_vocab",
        lambda base_dir, logger, slug: {"dummy": {"aliases": {"dummy"}}},
        raising=True,
    )

    ctx = _Ctx(base_dir=base, repo_root_dir=base, raw_dir=raw, book_dir=book, slug="dummy")
    logger = _logger("test.obs.build")

    caplog.set_level(logging.INFO)
    _ = sapi.build_markdown_book(ctx, logger, slug="dummy")

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
    base = tmp_path / "output" / "timmy-kb-dummy"
    _write_minimal_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    ctx = _Ctx(base_dir=base, repo_root_dir=base, raw_dir=base / "raw", book_dir=book, slug="dummy")
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

    monkeypatch.setattr(semb, "_insert_chunks", _boom)

    caplog.set_level(logging.INFO)
    import pytest

    with pytest.raises(RuntimeError):
        sapi.index_markdown_to_db(ctx, logger, slug="dummy", scope="book", embeddings_client=Emb(), db_path=None)

    failed = next(
        r for r in caplog.records if r.msg == "phase_failed" and getattr(r, "phase", None) == "index_markdown_to_db"
    )
    assert getattr(failed, "status", None) == "failed"
    assert "db boom" in str(getattr(failed, "error", ""))
