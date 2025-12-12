# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import time
from pathlib import Path
from typing import List

import pytest

import semantic.api as sapi
from semantic import embedding_service


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.md_dir = base / "book"
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
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    # Due file di contenuto (no README/SUMMARY)
    (book / "a.md").write_text("# A\nBody\n", encoding="utf-8")
    (book / "b.md").write_text("# B\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _NoopLogger()
    db_path = tmp_path / "kb.sqlite"

    import kb_db as kdb

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
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (book / f"f{i}.md").write_text(f"# F{i}\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    logger = _NoopLogger()
    db_path = tmp_path / "kb2.sqlite"

    def run(db_file: Path) -> float:
        t0 = time.perf_counter()
        _ = sapi.index_markdown_to_db(
            ctx, logger, slug=ctx.slug, scope="book", embeddings_client=_EmbClient(), db_path=db_file
        )
        return time.perf_counter() - t0

    def measure(db_file: Path) -> float:
        return min(run(db_file) for _ in range(2))

    dt_single = measure(db_path)
    dt_repeat = measure(tmp_path / "kb_repeat_1.sqlite") + measure(tmp_path / "kb_repeat_2.sqlite")

    # Con un solo init il costo rimane significativamente inferiore rispetto a due init separati.
    assert dt_single <= dt_repeat * 0.75
