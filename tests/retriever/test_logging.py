# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from typing import Any

import pytest

from tests.conftest import DUMMY_SLUG
from timmy_kb.cli.retriever import QueryParams, search


class _DummyEmbeddingsClient:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def embed_texts(self, texts: list[str]) -> Any:
        return self._payload


@pytest.fixture(autouse=True)
def _no_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("timmy_kb.cli.retriever.fetch_candidates", lambda *args, **kwargs: [], raising=True)


def _base_params(query: str) -> QueryParams:
    return QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query=query,
        k=3,
    )


@pytest.mark.parametrize(
    ("query", "payload", "reason"),
    (
        ("   ", [[0.1, 0.2]], "empty_query"),
        ("ciao", [], "empty_embedding"),
    ),
)
def test_search_logs_invalid_input(
    caplog: pytest.LogCaptureFixture, query: str, payload: list[list[float]], reason: str
) -> None:
    params = _base_params(query)
    client = _DummyEmbeddingsClient(payload)

    with caplog.at_level(logging.WARNING):
        out = search(params, client)
    assert out == []
    record = next(
        (
            rec
            for rec in reversed(caplog.records)
            if rec.getMessage() == "retriever.query.invalid" and getattr(rec, "reason", None) == reason
        ),
        None,
    )
    assert record is not None
    assert getattr(record, "slug") == DUMMY_SLUG
    assert getattr(record, "scope") == "kb"


def test_search_logs_embedding_failure(caplog: pytest.LogCaptureFixture) -> None:
    params = _base_params("ciao")

    class _BoomClient:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        out = search(params, _BoomClient())
    assert out == []
    record = next(
        (rec for rec in reversed(caplog.records) if rec.getMessage() == "retriever.query.embed_failed"),
        None,
    )
    assert record is not None
    assert getattr(record, "slug") == DUMMY_SLUG
    assert getattr(record, "scope") == "kb"
    assert "boom" in str(getattr(record, "error", ""))
