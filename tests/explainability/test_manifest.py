# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from explainability.manifest import SNIPPET_MAX_LEN, build_response_manifest
from timmy_kb.cli.retriever import QueryParams


def _build_params(tmp_path: Path, **overrides: Any) -> QueryParams:
    base = {
        "db_path": tmp_path / "kb.sqlite",
        "slug": "acme",
        "scope": "kb",
        "query": "ciao",
        "k": 1,
        "candidate_limit": 500,
    }
    base.update(overrides)
    return QueryParams(**base)


def _make_result(
    *,
    content: str,
    score: float,
    source_id: str | None = None,
    chunk_id: str | None = None,
    path: str | None = None,
) -> dict:
    lineage = {"source_id": source_id, "chunks": [{"chunk_id": chunk_id, "path": path}]} if source_id else None
    meta: dict[str, object] = {}
    if path:
        meta["path"] = path
    if lineage:
        meta["lineage"] = lineage
    return {
        "content": content,
        "meta": meta,
        "score": score,
    }


def test_build_response_manifest_includes_lineage_and_ranks(tmp_path: Path) -> None:
    params = _build_params(tmp_path, k=2)
    results = [
        _make_result(content="foo", score=0.9, source_id="s1", chunk_id="c1", path="book/foo.md"),
        _make_result(content="bar", score=0.5, source_id="s2", chunk_id="c2", path="book/bar.md"),
    ]

    manifest = build_response_manifest(results, params, "resp-1", slug="acme", scope="kb")

    assert manifest["response_id"] == "resp-1"
    assert manifest["slug"] == "acme"
    assert manifest["scope"] == "kb"
    assert manifest["query"] == "ciao"
    assert manifest["retriever_params"]["k"] == 2
    assert manifest["retriever_params"]["candidate_limit"] == 500
    assert len(manifest["evidence"]) == 2
    assert manifest["evidence"][0]["rank"] == 1
    assert manifest["evidence"][0]["source_id"] == "s1"
    assert manifest["evidence"][1]["rank"] == 2
    assert manifest["evidence"][1]["chunk_id"] == "c2"
    assert manifest["metrics"]["candidates_loaded"] == 2
    assert manifest["metrics"]["evaluated"] == 2
    assert manifest["lineage_refs"][0]["source_id"] == "s1"
    assert manifest["lineage_refs"][1]["chunk_id"] == "c2"


def test_build_response_manifest_snippet_limit(tmp_path: Path) -> None:
    params = _build_params(tmp_path)
    long_content = "a" * (SNIPPET_MAX_LEN + 10)
    results = [_make_result(content=long_content, score=0.9, source_id="s1", chunk_id="c1")]

    manifest = build_response_manifest(results, params, "resp-2", slug="acme", scope="kb", snippet_max_len=50)

    assert manifest["evidence"][0]["snippet"] == long_content[:50]
    assert len(manifest["evidence"][0]["snippet"]) == 50


def test_build_response_manifest_handles_missing_lineage(tmp_path: Path) -> None:
    params = _build_params(tmp_path)
    results = [{"content": "foo", "meta": {}, "score": 0.1}]

    manifest = build_response_manifest(results, params, "resp-3", slug="acme", scope="kb")

    assert manifest["evidence"][0]["source_id"] is None
    assert manifest["evidence"][0]["chunk_id"] is None
    assert manifest["lineage_refs"][0]["source_id"] is None
    assert manifest["lineage_refs"][0]["chunk_id"] is None


def test_build_response_manifest_is_idempotent_except_timestamp(tmp_path: Path) -> None:
    params = _build_params(tmp_path)
    results = [_make_result(content="foo", score=0.9, source_id="s1", chunk_id="c1", path="book/foo.md")]

    manifest_a = build_response_manifest(results, params, "resp-4", slug="acme", scope="kb")
    manifest_b = build_response_manifest(results, params, "resp-4", slug="acme", scope="kb")

    manifest_a_no_ts = deepcopy(manifest_a)
    manifest_b_no_ts = deepcopy(manifest_b)
    manifest_a_no_ts.pop("timestamp", None)
    manifest_b_no_ts.pop("timestamp", None)

    assert manifest_a_no_ts == manifest_b_no_ts
