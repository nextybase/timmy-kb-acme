# SPDX-License-Identifier: GPL-3.0-only
# tests/retriever/test_security_hooks.py
from __future__ import annotations

from typing import Any

import pytest

from pipeline.exceptions import RetrieverError
from security.throttle import reset_token_buckets, throttle_token_bucket
from tests.conftest import DUMMY_SLUG
from timmy_kb.cli.retriever import QueryParams, search


class _DummyEmbeddingsClient:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def embed_texts(self, texts: list[str]) -> Any:
        return self._payload


@pytest.fixture(autouse=True)
def _stub_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("timmy_kb.cli.retriever.fetch_candidates", lambda *args, **kwargs: [], raising=True)


def _base_params(query: str = "hello") -> QueryParams:
    return QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query=query,
        k=1,
    )


def test_search_denied_by_authorizer(monkeypatch: pytest.MonkeyPatch) -> None:
    params = _base_params()
    client = _DummyEmbeddingsClient([[0.1, 0.2, 0.3]])

    def _deny_authorizer(p: QueryParams) -> None:
        raise RetrieverError("denied")

    with pytest.raises(RetrieverError, match="denied"):
        search(params, client, authorizer=_deny_authorizer)


def test_search_throttle_blocks_after_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_token_buckets()
    monkeypatch.setenv("TIMMY_USER_EMAIL", "user@example.com")

    params = _base_params()
    client = _DummyEmbeddingsClient([[0.1, 0.2, 0.3]])

    def _limited_throttle(p: QueryParams) -> None:
        throttle_token_bucket(p, max_requests=2, interval_seconds=300)

    # Prime due passano
    assert search(params, client, throttle_check=_limited_throttle) == []
    assert search(params, client, throttle_check=_limited_throttle) == []

    with pytest.raises(RetrieverError, match="rate limit"):
        search(params, client, throttle_check=_limited_throttle)
