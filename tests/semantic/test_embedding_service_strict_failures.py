# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import semantic.api as sapi
from pipeline.exceptions import ConfigError
from tests.support.contexts import TestClientCtx
from tests.utils.workspace import ensure_minimal_workspace_layout


def _ctx(base: Path) -> TestClientCtx:
    return TestClientCtx(
        slug="dummy",
        repo_root_dir=base,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )


def test_index_markdown_to_db_hard_fails_on_embedding_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    ensure_minimal_workspace_layout(base, client_name="dummy")
    book_dir = base / "book"
    (book_dir / "a.md").write_text("# A\ncontenuto", encoding="utf-8")
    db_path = base / "semantic" / "kb.sqlite"
    monkeypatch.setenv("TEST_MODE", "1")

    class _BoomEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            _ = (texts, model)
            raise RuntimeError("boom")

    with pytest.raises(ConfigError, match="Embedding computation failed for slug=dummy"):
        sapi.index_markdown_to_db(
            _ctx(base),
            logging.getLogger("test.embedding.fail"),
            slug="dummy",
            scope="book",
            embeddings_client=_BoomEmb(),
            db_path=db_path,
        )


def test_index_markdown_to_db_returns_inserted_gt_zero_on_valid_embeddings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    ensure_minimal_workspace_layout(base, client_name="dummy")
    book_dir = base / "book"
    (book_dir / "a.md").write_text("# A\ncontenuto", encoding="utf-8")
    db_path = base / "semantic" / "kb.sqlite"
    monkeypatch.setenv("TEST_MODE", "1")

    class _OkEmb:
        def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
            _ = model
            return [[0.1, 0.2, 0.3] for _ in texts]

    inserted = sapi.index_markdown_to_db(
        _ctx(base),
        logging.getLogger("test.embedding.ok"),
        slug="dummy",
        scope="book",
        embeddings_client=_OkEmb(),
        db_path=db_path,
    )
    assert inserted > 0
