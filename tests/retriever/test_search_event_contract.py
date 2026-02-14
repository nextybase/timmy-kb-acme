# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import RetrieverError
from timmy_kb.cli import retriever


class _DummyEmbeddingsClient:
    model = "test-embed-model"


def _params(tmp_path: Path, *, query: str = "hello", k: int = 3) -> retriever.QueryParams:
    return retriever.QueryParams(
        db_path=(tmp_path / "kb.sqlite").resolve(),
        slug="dummy",
        scope="kb",
        query=query,
        k=k,
    )


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [rec.getMessage() for rec in caplog.records]


def _assert_relative_order(messages: list[str], expected: list[str]) -> None:
    cursor = 0
    for event in expected:
        idx = messages.index(event, cursor)
        cursor = idx + 1


def test_search_event_contract_happy_path(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    params = _params(tmp_path)
    client = _DummyEmbeddingsClient()

    monkeypatch.setattr(retriever, "_throttle_guard", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(retriever.embeddings_mod, "_materialize_query_vector", lambda *_a, **_k: ([0.1, 0.2], 1.23))
    monkeypatch.setattr(
        retriever,
        "fetch_candidates",
        lambda *_a, **_k: [
            {
                "content": "c1",
                "meta": {"lineage": {"source_id": "s1", "chunks": [{"chunk_id": "ch1"}]}},
                "embedding": [0.1],
            },
            {
                "content": "c2",
                "meta": {"lineage": {"source_id": "s2", "chunks": [{"chunk_id": "ch2"}]}},
                "embedding": [0.2],
            },
        ],
    )
    monkeypatch.setattr(
        retriever.ranking_mod,
        "_rank_candidates",
        lambda *_a, **_k: (
            [
                {
                    "content": "c1",
                    "meta": {"lineage": {"source_id": "s1", "chunks": [{"chunk_id": "ch1"}]}},
                    "score": 0.9,
                }
            ],
            2,
            {"short": 0, "normalized": 0, "skipped": 0},
            2.5,
            2,
            False,
        ),
    )
    monkeypatch.setattr(retriever.manifest_mod, "_write_manifest_if_configured", lambda **_k: None)

    caplog.set_level(logging.INFO, logger=retriever.LOGGER.name)
    out = retriever.search(
        params,
        client,
        response_id="r-1",
        throttle=retriever.ThrottleSettings(latency_budget_ms=500, parallelism=1, sleep_ms_between_calls=0),
    )

    assert out and isinstance(out, list)
    messages = _messages(caplog)
    _assert_relative_order(
        messages,
        [
            "retriever.query.started",
            "retriever.query.embedded",
            "retriever.candidates.fetched",
            "retriever.throttle.metrics",
        ],
    )

    started = next(rec for rec in caplog.records if rec.getMessage() == "retriever.query.started")
    fetched = next(rec for rec in caplog.records if rec.getMessage() == "retriever.candidates.fetched")
    assert hasattr(started, "candidate_limit")
    assert hasattr(started, "response_id")
    assert hasattr(fetched, "candidates_loaded")
    assert hasattr(fetched, "budget_hit")


def test_search_event_contract_deadline_preflight_soft_fail(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    params = _params(tmp_path)
    client = _DummyEmbeddingsClient()

    monkeypatch.setattr(retriever.throttle_mod, "_deadline_exceeded", lambda _d: True)

    caplog.set_level(logging.WARNING, logger=retriever.LOGGER.name)
    out = retriever.search(
        params,
        client,
        response_id="r-preflight",
        throttle=retriever.ThrottleSettings(latency_budget_ms=1, parallelism=1, sleep_ms_between_calls=0),
    )

    assert out == []
    assert "retriever.throttle.deadline" in _messages(caplog)


def test_search_event_contract_embed_failed_soft_fail(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    params = _params(tmp_path)
    client = _DummyEmbeddingsClient()

    monkeypatch.setattr(retriever, "_throttle_guard", lambda *_a, **_k: nullcontext())
    monkeypatch.setattr(retriever.throttle_mod, "_deadline_exceeded", lambda _d: False)

    def _raise_embed(*_a: Any, **_k: Any) -> tuple[list[float], float]:
        raise RetrieverError("embed boom")

    monkeypatch.setattr(retriever.embeddings_mod, "_materialize_query_vector", _raise_embed)

    caplog.set_level(logging.WARNING, logger=retriever.LOGGER.name)
    out = retriever.search(params, client, response_id="r-embed-fail")

    assert out == []
    assert "retriever.query.embed_failed" in _messages(caplog)
