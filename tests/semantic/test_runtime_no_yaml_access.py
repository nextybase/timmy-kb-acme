# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from semantic.api import index_markdown_to_db
from tests._helpers.workspace_paths import local_workspace_dir, local_workspace_name
from tests.conftest import DUMMY_SLUG
from tests.utils.workspace import ensure_minimal_workspace_layout
from timmy_kb.cli import retriever as retriever_api

LOCAL_WORKSPACE_NAME = local_workspace_name(DUMMY_SLUG)


@dataclass
class _Ctx:
    repo_root_dir: Path
    raw_dir: Path
    book_dir: Path
    slug: str


def _ctx(repo_root_dir: Path) -> _Ctx:
    ensure_minimal_workspace_layout(repo_root_dir, client_name=DUMMY_SLUG)
    return _Ctx(
        repo_root_dir=repo_root_dir,
        raw_dir=repo_root_dir / "raw",
        book_dir=repo_root_dir / "book",
        slug=DUMMY_SLUG,
    )


def _workspace_root(tmp_path: Path) -> Path:
    base_parent = tmp_path / "output"
    base = local_workspace_dir(base_parent, DUMMY_SLUG)
    assert base.name == LOCAL_WORKSPACE_NAME
    return base


class _IndexEmbeddings:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        return [[0.6, 0.4] for _ in texts]


class _QueryEmbeddings:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        return [[0.6, 0.4] for _ in texts]


def test_runtime_index_and_search_do_not_read_tags_reviewed_yaml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base = _workspace_root(tmp_path)
    book = base / "book"
    semantic_dir = base / "semantic"
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    (book / "Doc.md").write_text("---\ntitle: Doc\n---\nContenuto runtime", encoding="utf-8")

    real_open = builtins.open
    real_read_text = Path.read_text

    def _guard_open(file: Any, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        try:
            p = Path(file)
        except Exception:
            return real_open(file, *args, **kwargs)
        if p.name == "tags_reviewed.yaml":
            raise AssertionError("Runtime path must not read semantic/tags_reviewed.yaml")
        return real_open(file, *args, **kwargs)

    def _guard_read_text(path_self: Path, *args: Any, **kwargs: Any) -> str:
        if path_self.name == "tags_reviewed.yaml":
            raise AssertionError("Runtime path must not read semantic/tags_reviewed.yaml")
        return cast(str, real_read_text(path_self, *args, **kwargs))

    monkeypatch.setattr(builtins, "open", _guard_open)
    monkeypatch.setattr(Path, "read_text", _guard_read_text)

    inserted = index_markdown_to_db(
        cast(Any, _ctx(base)),
        logging.getLogger("test.runtime.no_yaml"),
        slug=DUMMY_SLUG,
        scope="book",
        embeddings_client=_IndexEmbeddings(),
    )
    assert inserted == 1

    db_path = semantic_dir / "kb.sqlite"
    params = retriever_api.QueryParams(
        db_path=db_path,
        slug=DUMMY_SLUG,
        scope="book",
        query="runtime",
        k=1,
        candidate_limit=retriever_api.MIN_CANDIDATE_LIMIT,
    )
    results = retriever_api.search(params, _QueryEmbeddings())

    assert len(results) == 1
    assert results[0]["meta"]["title"] == "Doc"
