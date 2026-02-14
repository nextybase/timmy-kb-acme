# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_semantic_index_markdown_db.py
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, cast

import numpy as np

import semantic.embedding_service as emb_service
from pipeline.exceptions import ConfigError
from semantic.api import index_markdown_to_db
from storage.kb_db import fetch_candidates
from tests._helpers.workspace_paths import local_workspace_dir, local_workspace_name
from tests.utils.workspace import ensure_minimal_workspace_layout


class _DummyEmbeddings:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        # restituisce vettori banali di dimensione fissa
        return [[float(len(t) % 5), 1.0, 0.5] for t in texts]


@dataclass
class C:
    repo_root_dir: Path
    raw_dir: Path
    book_dir: Path
    slug: str


def _ctx(repo_root_dir: Path) -> C:
    ensure_minimal_workspace_layout(repo_root_dir, client_name="dummy")
    return C(
        repo_root_dir=repo_root_dir,
        raw_dir=repo_root_dir / "raw",
        book_dir=repo_root_dir / "book",
        slug="dummy",
    )


CLIENT_SLUG = "dummy"
LOCAL_WORKSPACE_NAME = local_workspace_name(CLIENT_SLUG)


def _dummy_workspace_root(tmp_path: Path) -> Path:
    base_parent = tmp_path / "output"
    base = local_workspace_dir(base_parent, CLIENT_SLUG)
    assert base.name == LOCAL_WORKSPACE_NAME
    return base


def test_index_markdown_to_db_inserts_rows(tmp_path):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\ncontenuto uno", encoding="utf-8")
    (book / "B.md").write_text("# B\ncontenuto due", encoding="utf-8")

    dbp = semantic_dir / "db.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),  # bypass nominal type di ClientContext
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=_DummyEmbeddings(),
        db_path=dbp,
    )
    assert inserted >= 2

    # Recupera alcuni candidati e verifica che arrivino dal DB
    cands = list(fetch_candidates("dummy", "book", limit=10, db_path=dbp))
    assert len(cands) >= 2


def test_index_markdown_to_db_numpy_array(tmp_path):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class NpEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return np.array([[1.0, 0.0], [0.5, 0.5]])

    dbp = semantic_dir / "db.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=NpEmb(),
        db_path=dbp,
    )
    assert inserted == 2
    cands = list(fetch_candidates("dummy", "book", limit=10, db_path=dbp))
    assert len(cands) >= 2


def test_index_markdown_to_db_generator_and_empty_vectors(tmp_path, caplog):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
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
        slug="dummy",
        scope="book",
        embeddings_client=GenEmb(),
        db_path=semantic_dir / "db_gen.sqlite",
    )
    assert ok == 1

    # Vettori di lunghezza zero -> hard-fail (niente fallback a 0)
    class EmptyVecEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[] for _ in texts]

    import pytest

    with pytest.raises(ConfigError, match="empty vectors|zero vectors|Embedding computation"):
        index_markdown_to_db(
            cast(Any, _ctx(base)),
            logging.getLogger("test"),
            slug="dummy",
            scope="book",
            embeddings_client=EmptyVecEmb(),
            db_path=semantic_dir / "db_empty.sqlite",
        )
    # Verifica i log strutturati emessi quando gli embeddings risultano vuoti
    assert any(r.getMessage() == "semantic.index.first_embedding_empty" for r in caplog.records)
    assert any(r.getMessage() == "semantic.index.all_embeddings_empty" for r in caplog.records)
    assert any(
        r.getMessage() == "semantic.index.all_embeddings_empty"
        and getattr(r, "event", None) == "semantic.index.all_embeddings_empty"
        for r in caplog.records
    )


def test_index_markdown_to_db_list_of_numpy_arrays(tmp_path):
    import logging
    from typing import Any, cast

    import numpy as np

    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class ListNpEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [np.array([1.0, 0.0]), np.array([0.5, 0.5])]

    dbp = semantic_dir / "db_list_np.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=ListNpEmb(),
        db_path=dbp,
    )
    assert inserted == 2


def test_index_markdown_to_db_mismatch_lengths_inserts_partial(tmp_path, caplog):
    import logging
    from typing import Any, cast

    import numpy as np

    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class ShortEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            # solo 1 embedding per forzare mismatch con 2 contenuti
            return [np.array([1.0, 0.0])]

    caplog.set_level(logging.INFO)
    ret = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=ShortEmb(),
        db_path=semantic_dir / "db_short.sqlite",
    )
    # nuovo comportamento: indicizzazione parziale sul minimo comune
    assert ret == 1
    msgs = [r.getMessage() for r in caplog.records]
    assert any("semantic.index.mismatched_embeddings" in m for m in msgs)
    assert any("semantic.index.embedding_pruned" in m for m in msgs)
    assert any("semantic.index.skips" in m for m in msgs)
    assert any("semantic.index.done" in m for m in msgs)

    pruned_records = [r for r in caplog.records if r.getMessage() == "semantic.index.embedding_pruned"]
    assert pruned_records
    pruned = pruned_records[-1]
    assert getattr(pruned, "cause", None) == "mismatch"
    assert getattr(pruned, "dropped", None) == 1
    assert getattr(pruned, "kept", None) == 1


def test_index_markdown_to_db_phase_failed_on_insert_error(tmp_path, caplog, monkeypatch):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")

    class OkEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[1.0, 0.0] for _ in texts]

    def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("db boom")

    monkeypatch.setattr(emb_service, "_insert_chunks", boom)

    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test")
    import pytest

    with pytest.raises(RuntimeError):
        index_markdown_to_db(
            cast(Any, _ctx(base)),
            logger,
            slug="dummy",
            scope="book",
            embeddings_client=OkEmb(),
            db_path=semantic_dir / "db_fail.sqlite",
        )

    # Dentro il phase_scope deve comparire phase_failed e non artifact_count
    failed = [r for r in caplog.records if r.msg == "phase_failed"]
    assert failed, "phase_failed non loggato"
    assert all("artifact_count" not in r.__dict__ for r in failed)


def test_index_excludes_readme_and_summary(tmp_path):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    # Contenuto reale
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    # File da escludere
    (book / "README.md").write_text("# R\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# S\n", encoding="utf-8")

    class E:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            # Deve essere chiamato solo per A.md
            return [[1.0, 0.0] for _ in texts]

    dbp = semantic_dir / "db_exclude.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=E(),
        db_path=dbp,
    )
    assert inserted == 1


def test_index_filters_empty_embeddings_per_item(tmp_path, caplog):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "A.md").write_text("# A\nuno", encoding="utf-8")
    (book / "B.md").write_text("# B\ndue", encoding="utf-8")

    class PartEmptyEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            # Primo vuoto, secondo valido
            return [[], [1.0, 0.5]]

    caplog.set_level(logging.INFO)
    dbp = semantic_dir / "db_filter.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=PartEmptyEmb(),
        db_path=dbp,
    )
    assert inserted == 1
    # Log di drop presente (accetta messaggio umano o evento strutturato)
    pruned_records = [r for r in caplog.records if r.getMessage() == "semantic.index.embedding_pruned"]
    assert pruned_records
    pruned = pruned_records[-1]
    assert getattr(pruned, "cause", None) == "empty_embedding"
    assert getattr(pruned, "dropped", None) == 1


def test_index_preserves_frontmatter_and_metadata(tmp_path):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    (book / "guide").mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "guide" / "Intro.md").write_text(
        """---
title: "Introduzione"
tags:
  - Alpha
  - Beta
source_category: guida
created_at: "2025-01-01T00:00:00"
---
Contenuto principale del capitolo.
""",
        encoding="utf-8",
    )

    class Emb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[1.0, 0.5, 0.25] for _ in texts]

    dbp = semantic_dir / "db_frontmatter.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=Emb(),
        db_path=dbp,
    )
    assert inserted == 1

    candidates = list(fetch_candidates("dummy", "book", limit=1, db_path=dbp))
    assert candidates, "nessun candidato restituito dal DB"
    candidate = candidates[0]
    assert candidate["content"] == "Contenuto principale del capitolo."
    assert candidate["meta"]["file"] == "guide/Intro.md"
    assert candidate["meta"]["title"] == "Introduzione"
    assert candidate["meta"]["source_category"] == "guida"
    assert candidate["meta"]["created_at"] == "2025-01-01T00:00:00"
    assert candidate["meta"]["tags"] == ["Alpha", "Beta"]


def test_lineage_persisted_in_markdown_index(tmp_path):
    base = _dummy_workspace_root(tmp_path)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "Lineage.md").write_text("# Lineage\nContenuto lineage", encoding="utf-8")

    class Emb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            return [[0.1, 0.2, 0.3] for _ in texts]

    dbp = semantic_dir / "db_lineage.sqlite"
    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=Emb(),
        db_path=dbp,
    )
    assert inserted == 1

    candidates = list(fetch_candidates("dummy", "book", limit=5, db_path=dbp))
    assert candidates, "nessun candidato restituito dal DB"
    meta = candidates[0]["meta"]
    assert "lineage" in meta
    lineage = meta["lineage"]
    assert lineage["source_id"]
    assert len(lineage["chunks"]) == 1
    chunk_info = lineage["chunks"][0]
    assert set(chunk_info.keys()) == {"chunk_index", "chunk_id", "embedding_id"}
    assert chunk_info["chunk_id"]
    assert chunk_info["embedding_id"]
