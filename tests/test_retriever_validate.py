# tests/test_retriever_validate.py
from __future__ import annotations

from typing import Sequence

import pytest

from src.retriever import (
    QueryParams,
    search,
    RetrieverError,
)  # <— usa la stessa classe del modulo sotto test
import src.retriever as r


class DummyEmbeddings:
    """Stub compatibile con il Protocol EmbeddingsClient.

    Firma conforme:
      embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Sequence[Sequence[float]]
    """

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        # In questi test non dovremmo mai arrivare qui; se succede, falliamo.
        raise AssertionError("embed_texts should not be called on invalid params")


class HappyEmbeddings:
    """Embeddings stub per i casi validi: restituisce un singolo vettore."""

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        return [[1.0]]


def _params(
    *,
    project_slug: str = "acme",
    scope: str = "kb",
    query: str = "q",
    k: int = 1,
    candidate_limit: int = r.MIN_CANDIDATE_LIMIT,
):
    """Costruttore tipizzato per evitare dict Any→str|int|None che confondono Pylance."""
    return QueryParams(
        db_path=None,
        project_slug=project_slug,
        scope=scope,
        query=query,
        k=k,
        candidate_limit=candidate_limit,
    )


def test_validate_params_empty_project_slug() -> None:
    with pytest.raises(RetrieverError, match="project_slug"):
        search(_params(project_slug="   "), DummyEmbeddings())


def test_validate_params_empty_scope() -> None:
    with pytest.raises(RetrieverError, match="scope"):
        search(_params(scope=""), DummyEmbeddings())


def test_validate_params_negative_candidate_limit() -> None:
    with pytest.raises(RetrieverError, match="candidate_limit"):
        search(_params(candidate_limit=-1), DummyEmbeddings())


def test_validate_params_candidate_limit_too_low() -> None:
    with pytest.raises(RetrieverError, match="candidate_limit"):
        search(_params(candidate_limit=r.MIN_CANDIDATE_LIMIT - 1), DummyEmbeddings())


def test_validate_params_candidate_limit_too_high() -> None:
    with pytest.raises(RetrieverError, match="candidate_limit"):
        search(_params(candidate_limit=r.MAX_CANDIDATE_LIMIT + 1), DummyEmbeddings())


def test_validate_params_candidate_limit_min_ok(monkeypatch) -> None:
    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: [])
    out = search(_params(candidate_limit=r.MIN_CANDIDATE_LIMIT), HappyEmbeddings())
    assert out == []


def test_validate_params_candidate_limit_max_ok(monkeypatch) -> None:
    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: [])
    out = search(_params(candidate_limit=r.MAX_CANDIDATE_LIMIT), HappyEmbeddings())
    assert out == []


def test_validate_params_negative_k() -> None:
    with pytest.raises(RetrieverError, match="k"):
        search(_params(k=-5), DummyEmbeddings())


def test_search_early_return_on_empty_query(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("fetch_candidates should not be called for empty query")

    monkeypatch.setattr(r, "fetch_candidates", _boom)
    out = search(_params(query="   "), DummyEmbeddings())
    assert out == []


def test_search_early_return_on_zero_k(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("fetch_candidates should not be called when k==0")

    monkeypatch.setattr(r, "fetch_candidates", _boom)
    out = search(_params(k=0), DummyEmbeddings())
    assert out == []


def test_search_early_return_on_zero_candidate_limit(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("fetch_candidates should not be called when candidate_limit==0")

    monkeypatch.setattr(r, "fetch_candidates", _boom)
    out = search(_params(candidate_limit=0), DummyEmbeddings())
    assert out == []
