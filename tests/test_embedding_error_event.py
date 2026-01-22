# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import semantic.api as sapi
import timmy_kb.cli.ingest as ingest_mod
from pipeline.logging_utils import get_structured_logger
from timmy_kb.cli.ingest import ingest_path


class _BoomEmb:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def _prepare_workspace(base: Path, *, slug: str) -> SimpleNamespace:
    raw_dir = base / "raw"
    book_dir = base / "book"
    semantic_dir = base / "semantic"
    logs_dir = base / "logs"
    config_dir = base / "config"
    raw_dir.mkdir(parents=True, exist_ok=True)
    book_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (book_dir / "README.md").write_text("# README\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    return SimpleNamespace(repo_root_dir=base, slug=slug)


def test_embedding_error_is_logged_and_fall_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    book = base / "book"
    db_path = base / "kb.sqlite"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody", encoding="utf-8")
    _prepare_workspace(base, slug="dummy")

    ctx = type("C", (), dict(base_dir=base, book_dir=book, repo_root_dir=base, slug="dummy"))()
    logger = get_structured_logger("tests.index.emb_error", context=ctx)

    caplog.set_level(logging.INFO, logger="tests.index.emb_error")

    result = sapi.index_markdown_to_db(
        ctx, logger, slug="dummy", scope="book", embeddings_client=_BoomEmb(), db_path=db_path
    )
    assert result == 0

    # Deve essere presente l'evento strutturato con dettaglio dell'errore
    events = [r for r in caplog.records if getattr(r, "event", r.getMessage()) == "semantic.index.embedding_error"]
    assert events, "Evento semantic.index.embedding_error non trovato"
    last = events[-1]
    assert "boom" in str(getattr(last, "error", "")), "Dettaglio errore mancante"
    assert getattr(last, "count", None) in (1, "1"), "Conteggio testi non coerente"


def test_explainability_events_emitted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    ctx = _prepare_workspace(base, slug="dummy")
    raw_dir = base / "raw"
    db_path = base / "kb.sqlite"
    content_path = raw_dir / "loggable.md"
    content_path.write_text("# Loggable\nContenuto eventi", encoding="utf-8")

    def _single_chunk(text: str, *, target_tokens: int = 400, overlap_tokens: int = 40) -> list[str]:
        return [text]

    monkeypatch.setattr(ingest_mod, "_chunk_text", _single_chunk, raising=True)

    class _OkEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[0.1, 0.2, 0.3] for _ in texts]

    caplog.set_level(logging.INFO, logger="timmy_kb.ingest")

    inserted = ingest_path(
        slug="dummy",
        scope="kb",
        path=str(content_path),
        version="v1",
        meta={},
        embeddings_client=_OkEmb(),
        context=ctx,
        base_dir=base,
        db_path=db_path,
    )
    assert inserted > 0

    events = {record.getMessage() for record in caplog.records}
    assert {
        "semantic.input.received",
        "semantic.lineage.chunk_created",
        "semantic.lineage.embedding_registered",
    } <= events

    chunk_records = [r for r in caplog.records if r.getMessage() == "semantic.lineage.chunk_created"]
    assert chunk_records
    chunk_rec = chunk_records[-1]
    assert getattr(chunk_rec, "chunk_id", None)
    assert getattr(chunk_rec, "chunk_index", None) in (0, "0")

    input_records = [r for r in caplog.records if r.getMessage() == "semantic.input.received"]
    assert input_records
    assert getattr(input_records[-1], "source_id", None)

    embedding_records = [r for r in caplog.records if r.getMessage() == "semantic.lineage.embedding_registered"]
    assert embedding_records
    assert getattr(embedding_records[-1], "source_id", None)
