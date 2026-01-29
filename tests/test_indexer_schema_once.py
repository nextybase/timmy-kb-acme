# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

import semantic.api as sapi
from semantic import embedding_service
from tests.utils.workspace import ensure_minimal_workspace_layout


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.repo_root_dir = base
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.book_dir = base / "book"
        self.slug = slug


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def debug(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _EmbClient:
    def embed_texts(self, texts: List[str]) -> List[List[float]]:  # noqa: D401
        return [[1.0, 0.0, 0.5] for _ in texts]


def test_indexer_initializes_schema_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    # Due file di contenuto (no README/SUMMARY)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")
    (book / "b.md").write_text("# B\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _NoopLogger()
    db_path = semantic_dir / "kb.sqlite"

    import storage.kb_db as kdb

    calls = {"init": 0}
    real_init = kdb.init_db

    def _counting_init(pth):
        calls["init"] += 1
        return real_init(pth)

    monkeypatch.setattr(kdb, "init_db", _counting_init, raising=True)
    # Patch anche il riferimento importato in semantic.api
    monkeypatch.setattr(embedding_service, "_init_kb_db", _counting_init, raising=True)

    inserted = sapi.index_markdown_to_db(
        ctx, logger, slug=ctx.slug, scope="book", embeddings_client=_EmbClient(), db_path=db_path
    )

    assert inserted >= 2  # almeno due contenuti indicizzati
    assert calls["init"] == 1


def test_indexer_reduces_overhead_with_single_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    ensure_minimal_workspace_layout(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (book / f"f{i}.md").write_text(f"# F{i}\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _NoopLogger()
    db_path = semantic_dir / "kb2.sqlite"

    import storage.kb_db as kdb

    calls: list[Path | None] = []
    real_init = kdb.init_db

    def _counting_init(pth: Path | None = None) -> None:
        calls.append(pth)
        return real_init(pth)

    monkeypatch.setattr(kdb, "init_db", _counting_init, raising=True)
    monkeypatch.setattr(embedding_service, "_init_kb_db", _counting_init, raising=True)

    def run(db_file: Path) -> int:
        before = len(calls)
        _ = sapi.index_markdown_to_db(
            ctx, logger, slug=ctx.slug, scope="book", embeddings_client=_EmbClient(), db_path=db_file
        )
        return len(calls) - before

    single_init_count = run(db_path) + run(db_path)
    repeat_count = run(semantic_dir / "kb_repeat_1.sqlite") + run(semantic_dir / "kb_repeat_2.sqlite")

    assert repeat_count >= 2
    assert single_init_count <= repeat_count
