# SPDX-License-Identifier: GPL-3.0-only
# tests/test_kb_db_insert.py
from pathlib import Path

from kb_db import insert_chunks
from semantic.api import index_markdown_to_db


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
        self.slug = slug


class _DummyEmbeddings:
    # Restituisce un vettore non vuoto per ciascun testo
    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.5] for _ in texts]


def test_insert_chunks_idempotency_and_index_aggregate(tmp_path: Path):
    db_path = tmp_path / "kb.sqlite"

    # Inserimento diretto a basso livello
    k1 = insert_chunks(
        project_slug="obs",
        scope="s",
        path="p",
        version="v",
        meta_dict={},
        chunks=["c1", "c2"],
        embeddings=[[1.0], [1.0]],
        db_path=db_path,
    )
    assert k1 == 2

    # Re-run identico: nessun nuovo inserimento
    k2 = insert_chunks(
        project_slug="obs",
        scope="s",
        path="p",
        version="v",
        meta_dict={},
        chunks=["c1", "c2"],
        embeddings=[[1.0], [1.0]],
        db_path=db_path,
    )
    assert k2 == 0

    # High-level: indicizzazione da book/
    base = tmp_path / "kb_out"
    book = base / "book"
    raw = base / "raw"
    book.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\n\n", encoding="utf-8")
    (book / "b.md").write_text("# B\n\n", encoding="utf-8")
    # README/SUMMARY ignorati
    (book / "README.md").write_text("# R\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    ctx = _Ctx(base, slug="proj")
    emb = _DummyEmbeddings()

    # Primo pass: 2 file contenuto -> 2 insert
    n1 = index_markdown_to_db(
        ctx,
        logger=_NoopLogger(),
        slug="proj",
        scope="book",
        embeddings_client=emb,
        db_path=db_path,
    )
    assert n1 == 2

    # Secondo pass identico: 0 insert
    n2 = index_markdown_to_db(
        ctx,
        logger=_NoopLogger(),
        slug="proj",
        scope="book",
        embeddings_client=emb,
        db_path=db_path,
    )
    assert n2 == 0


class _NoopLogger:
    def info(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def warning(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def debug(self, *a, **k):  # noqa: D401
        """No-op."""
        pass

    def error(self, *a, **k):  # noqa: D401
        """No-op."""
        pass
