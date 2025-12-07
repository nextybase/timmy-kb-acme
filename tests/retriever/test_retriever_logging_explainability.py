# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List

import pytest
from tests.conftest import DUMMY_SLUG

from retriever import QueryParams, search


class _DummyEmbeddingsClient:
    def __init__(self, vector: List[float]) -> None:
        self._vector = vector
        self.model = "embed-model"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


def _fake_candidates_with_lineage(*_: Any, **__: Any) -> list[dict[str, Any]]:
    return [
        {
            "content": "foo content",
            "meta": {"lineage": {"source_id": "s1", "chunks": [{"chunk_id": "c1"}]}},
            "embedding": [0.1, 0.2, 0.3],
        },
        {
            "content": "bar content",
            "meta": {"lineage": {"source_id": "s2", "chunks": [{"chunk_id": "c2"}]}},
            "embedding": [0.2, 0.1, 0.0],
        },
    ]


def test_retriever_logs_explainability_events(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("retriever.fetch_candidates", _fake_candidates_with_lineage, raising=True)
    params = QueryParams(db_path=None, slug=DUMMY_SLUG, scope="kb", query="hello world", k=2, candidate_limit=800)
    client = _DummyEmbeddingsClient([0.1, 0.1, 0.1])

    assert len(list(_fake_candidates_with_lineage())) == 2
    assert len(list(search.__globals__["fetch_candidates"](params.slug, params.scope, limit=2))) == 2

    with caplog.at_level(logging.INFO):
        _ = search(params, client, response_id="resp-xyz", embedding_model="embed-model")
    started = next((rec for rec in caplog.records if rec.getMessage() == "retriever.query.started"), None)
    assert started is not None
    assert getattr(started, "response_id") == "resp-xyz"
    assert getattr(started, "candidate_limit") == 800
    assert getattr(started, "query_len") == len("hello world")

    embedded = next((rec for rec in caplog.records if rec.getMessage() == "retriever.query.embedded"), None)
    assert embedded is not None
    assert getattr(embedded, "embedding_dims") == 3
    assert getattr(embedded, "embedding_model") == "embed-model"

    fetched = next((rec for rec in caplog.records if rec.getMessage() == "retriever.candidates.fetched"), None)
    assert fetched is not None
    assert getattr(fetched, "candidates_loaded") == 2
    assert getattr(fetched, "candidate_limit") == 800
    assert getattr(fetched, "budget_hit") is False

    selected = next((rec for rec in caplog.records if rec.getMessage() == "retriever.evidence.selected"), None)
    assert selected is not None
    assert getattr(selected, "selected_count") == 2
    evidence_ids = getattr(selected, "evidence_ids")
    assert isinstance(evidence_ids, list)
    assert evidence_ids[0]["rank"] == 1
    assert evidence_ids[0]["source_id"] == "s1"
    assert evidence_ids[1]["chunk_id"] == "c2"


def test_response_manifest_event_emitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("retriever.fetch_candidates", _fake_candidates_with_lineage, raising=True)
    params = QueryParams(db_path=None, slug=DUMMY_SLUG, scope="kb", query="hello world", k=1, candidate_limit=600)
    client = _DummyEmbeddingsClient([0.1, 0.1, 0.1])

    with caplog.at_level(logging.INFO):
        search(params, client, response_id="resp-manifest", embedding_model="embed-model", explain_base_dir=tmp_path)

    manifest_event = next((rec for rec in caplog.records if rec.getMessage() == "retriever.response.manifest"), None)
    assert manifest_event is not None
    assert getattr(manifest_event, "response_id") == "resp-manifest"
    assert Path(getattr(manifest_event, "manifest_path")).name == "resp-manifest.json"
    assert getattr(manifest_event, "evidence_ids")[0]["chunk_id"] == "c1"


def test_retriever_logging_handles_missing_lineage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _fake_candidates_no_lineage(*_: Any, **__: Any) -> list[dict[str, Any]]:
        return [{"content": "foo", "meta": {}, "embedding": [0.1, 0.2]}]

    monkeypatch.setattr("retriever.fetch_candidates", _fake_candidates_no_lineage, raising=True)
    params = QueryParams(db_path=None, slug=DUMMY_SLUG, scope="kb", query="hi", k=1, candidate_limit=600)
    client = _DummyEmbeddingsClient([0.1, 0.2])

    with caplog.at_level(logging.INFO):
        _ = search(params, client, response_id="resp-no-lineage")

    selected = next((rec for rec in caplog.records if rec.getMessage() == "retriever.evidence.selected"), None)
    assert selected is not None
    evidence_ids = getattr(selected, "evidence_ids")
    assert evidence_ids[0]["source_id"] is None
    assert evidence_ids[0]["chunk_id"] is None
