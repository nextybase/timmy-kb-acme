# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

import semantic.api as sapi
from pipeline.exceptions import ConfigError
from semantic import embedding_service


class _Ctx:
    def __init__(self, base: Path, slug: str = "proj"):
        self.repo_root_dir = base
        self.base_dir = base
        self.raw_dir = base / "raw"
        self.book_dir = base / "book"
        self.slug = slug
        self.config_dir = base / "config"
        self.normalized_dir = base / "normalized"
        self.semantic_dir = base / "semantic"
        self.logs_dir = base / "logs"
        for child in (
            self.raw_dir,
            self.normalized_dir,
            self.book_dir,
            self.semantic_dir,
            self.logs_dir,
            self.config_dir,
        ):
            child.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")


class _NoopLogger:
    def info(self, *a, **k): ...

    def warning(self, *a, **k): ...

    def debug(self, *a, **k): ...

    def error(self, *a, **k): ...


class _EmbClient:
    def embed_texts(self, texts: List[str]) -> List[List[float]]:  # noqa: D401
        # ritorna un vettore finto per ogni testo
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_indexer_init_db_failfast_raises_configerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "kb"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir = base / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("---\ntitle: A\n---\n# A\nBody\n", encoding="utf-8")

    ctx = _Ctx(base)
    (book / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")
    logger = _NoopLogger()
    db_path = semantic_dir / "kb.sqlite"

    import sqlite3

    # Fingi che l'init del DB fallisca subito con errore SQLite
    def _boom(_pth):
        raise sqlite3.OperationalError("init failed")

    monkeypatch.setattr(embedding_service, "_init_kb_db", _boom, raising=True)

    with pytest.raises(ConfigError) as ei:
        _ = sapi.index_markdown_to_db(
            ctx, logger, slug=ctx.slug, scope="book", embeddings_client=_EmbClient(), db_path=db_path
        )

    err = ei.value
    # path deve essere quello passato esplicitamente
    assert Path(getattr(err, "file_path", "")) == db_path
    assert getattr(err, "slug", None) == ctx.slug
