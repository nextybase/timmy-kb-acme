# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

import semantic.embedding_service as embedding_service
from pipeline.types import ChunkRecord


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.repo_root_dir = base
        self.base_dir = base
        self.book_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _RecordingLogger(_NoopLogger):
    def __init__(self):
        self.events: list[tuple[str, dict[str, object] | None]] = []

    def info(self, *args, **kwargs):
        super().info(*args, **kwargs)
        msg = args[0] if args else ""
        extra = kwargs.get("extra")
        self.events.append((msg, extra))


class _EmbClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:  # noqa: D401
        return [[1.0, 0.0, 0.5] for _ in texts]


def test_indexer_accepts_chunk_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    ctx = _Ctx(base)
    logger = _NoopLogger()
    inserted_meta: dict[str, object] | None = None

    record: ChunkRecord = ChunkRecord(
        id="chunk-1",
        slug=ctx.slug,
        source_path="book/a.md",
        text="# A\nBody\n",
        chunk_index=0,
        created_at="2025-12-14T00:00:00Z",
        metadata={"tags": ["test"], "layout_section": "intro"},
    )

    def fake_insert_chunks(*, meta_dict: dict[str, object], **kwargs):
        nonlocal inserted_meta
        inserted_meta = dict(meta_dict)
        return 1

    monkeypatch.setattr(embedding_service, "_insert_chunks", fake_insert_chunks)
    monkeypatch.setattr(embedding_service, "_init_kb_db", lambda db_path: None)

    inserted = embedding_service.index_markdown_to_db(
        base_dir=base,
        book_dir=book,
        slug=ctx.slug,
        logger=logger,
        scope="book",
        embeddings_client=_EmbClient(),
        db_path=tmp_path / "kb.sqlite",
        chunk_records=[record],
    )

    assert inserted == 1
    assert inserted_meta is not None
    assert inserted_meta["chunk_index"] == 0
    assert inserted_meta["source_path"] == "book/a.md"
    assert inserted_meta["created_at"] == "2025-12-14T00:00:00Z"
    assert inserted_meta["slug"] == ctx.slug


def test_indexer_chunking_heading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "doc.md").write_text("# Intro\nCiao\n# Details\nContenuti", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _NoopLogger()
    inserted_meta: list[dict[str, object]] = []

    def fake_insert_chunks(*, meta_dict: dict[str, object], **kwargs):
        inserted_meta.append(meta_dict)
        return 1

    monkeypatch.setattr(embedding_service, "_insert_chunks", fake_insert_chunks)
    monkeypatch.setattr(embedding_service, "_init_kb_db", lambda db_path: None)

    inserted = embedding_service.index_markdown_to_db(
        base_dir=base,
        book_dir=book,
        slug=ctx.slug,
        logger=logger,
        scope="book",
        embeddings_client=_EmbClient(),
        db_path=tmp_path / "kb.sqlite",
    )

    assert inserted >= 1
    assert len(inserted_meta) == 2
    first_meta, second_meta = inserted_meta
    assert first_meta["layout_section"] == "Intro"
    assert second_meta["layout_section"] == "Details"


def test_indexer_skipped_paths_only_missing_files_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "doc.md").write_text("# Section\nContenuto", encoding="utf-8")
    (book / "empty.md").write_text("", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _RecordingLogger()
    inserted_paths: list[str] = []

    def fake_insert_chunks(*, meta_dict: dict[str, object], **kwargs):
        inserted_paths.append(meta_dict["file"])
        return 1

    monkeypatch.setattr(embedding_service, "_insert_chunks", fake_insert_chunks)
    monkeypatch.setattr(embedding_service, "_init_kb_db", lambda db_path: None)

    inserted = embedding_service.index_markdown_to_db(
        base_dir=base,
        book_dir=book,
        slug=ctx.slug,
        logger=logger,
        scope="book",
        embeddings_client=_EmbClient(),
        db_path=tmp_path / "kb.sqlite",
    )

    assert inserted >= 1
    skip_files = [
        extra["file_path"] for msg, extra in logger.events if msg == "semantic.index.skip_empty_file" and extra
    ]
    assert skip_files == ["empty.md"]
    assert "doc.md" in inserted_paths
