# tests/test_semantic_index_markdown_db.py
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class _DummyEmbeddings:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        # restituisce vettori banali di dimensione fissa
        return [[float(len(t) % 5), 1.0, 0.5] for t in texts]


@dataclass
class C:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def _ctx(base_dir: Path) -> C:
    return C(
        base_dir=base_dir,
        raw_dir=base_dir / "raw",
        md_dir=base_dir / "book",
        slug="x",
    )


def test_index_markdown_to_db_inserts_rows(tmp_path):
    from kb_db import fetch_candidates
    from semantic.api import index_markdown_to_db

    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\ncontenuto uno", encoding="utf-8")
    (book / "B.md").write_text("# B\ncontenuto due", encoding="utf-8")

    dbp = tmp_path / "db.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),  # bypass nominal type di ClientContext
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=_DummyEmbeddings(),
        db_path=dbp,
    )
    assert inserted >= 2

    # Recupera alcuni candidati e verifica che arrivino dal DB
    cands = list(fetch_candidates("x", "book", limit=10, db_path=dbp))
    assert len(cands) >= 2
