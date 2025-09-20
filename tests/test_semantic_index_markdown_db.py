# tests/test_semantic_index_markdown_db.py
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, cast

import numpy as np

import semantic.api as api
from kb_db import fetch_candidates
from semantic.api import index_markdown_to_db


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


def test_index_markdown_to_db_numpy_array(tmp_path):
    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class NpEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return np.array([[1.0, 0.0], [0.5, 0.5]])

    dbp = tmp_path / "db.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=NpEmb(),
        db_path=dbp,
    )
    assert inserted == 2
    cands = list(fetch_candidates("x", "book", limit=10, db_path=dbp))
    assert len(cands) >= 2


def test_index_markdown_to_db_generator_and_empty_vectors(tmp_path, caplog):
    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")

    # Generatore coerente
    class GenEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            def _gen() -> Iterable[list[float]]:
                for _ in texts:
                    yield [1.0, 0.0]

            return _gen()

    caplog.set_level(logging.INFO)
    ok = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=GenEmb(),
        db_path=tmp_path / "db_gen.sqlite",
    )
    assert ok == 1

    # Vettori di lunghezza zero -> warning e ritorno 0
    class EmptyVecEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[] for _ in texts]

    ret = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=EmptyVecEmb(),
        db_path=tmp_path / "db_empty.sqlite",
    )
    assert ret == 0
    assert any("Primo vettore embedding vuoto" in r.getMessage() for r in caplog.records)


def test_index_markdown_to_db_list_of_numpy_arrays(tmp_path):
    import logging
    from typing import Any, cast

    import numpy as np

    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class ListNpEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [np.array([1.0, 0.0]), np.array([0.5, 0.5])]

    dbp = tmp_path / "db_list_np.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=ListNpEmb(),
        db_path=dbp,
    )
    assert inserted == 2


def test_index_markdown_to_db_mismatch_lengths_returns_0(tmp_path, caplog):
    import logging
    from typing import Any, cast

    import numpy as np

    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class ShortEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [np.array([1.0, 0.0])]

    caplog.set_level(logging.INFO)
    ret = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="x",
        scope="book",
        embeddings_client=ShortEmb(),
        db_path=tmp_path / "db_short.sqlite",
    )
    assert ret == 0


def test_index_markdown_to_db_phase_failed_on_insert_error(tmp_path, caplog, monkeypatch):
    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")

    class OkEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[1.0, 0.0] for _ in texts]

    def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("db boom")

    monkeypatch.setattr(api, "_insert_chunks", boom)

    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test")
    import pytest

    with pytest.raises(RuntimeError):
        index_markdown_to_db(
            cast(Any, _ctx(base)),
            logger,
            slug="x",
            scope="book",
            embeddings_client=OkEmb(),
            db_path=tmp_path / "db_fail.sqlite",
        )

    # Dentro il phase_scope deve comparire phase_failed e non artifact_count
    failed = [r for r in caplog.records if r.msg == "phase_failed"]
    assert failed, "phase_failed non loggato"
    assert all("artifact_count" not in r.__dict__ for r in failed)
