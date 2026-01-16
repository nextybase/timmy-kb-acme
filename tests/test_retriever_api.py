# SPDX-License-Identifier: GPL-3.0-only
"""Tests for retriever.search API.

Verifica:
- pass-through dei parametri via QueryParams verso fetch_candidates
- compatibilità con EmbeddingsClient (protocollo) e top-k
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

import timmy_kb.cli.retriever as retr
from tests.conftest import DUMMY_SLUG
from timmy_kb.cli.retriever import QueryParams


class FakeEmb:
    """Finto client embeddings conforme al protocollo (firma con argomento keyword-only `model`)."""

    def __init__(self) -> None:
        self.calls: list[Sequence[str]] = []
        self.last_model: str | None = None

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Sequence[float]]:
        """Ritorna un embedding unitario e registra le chiamate per l'asserzione."""
        self.calls.append(tuple(texts))
        self.last_model = model
        return [[1.0, 0.0]]


def test_search_uses_query_params_and_limit(monkeypatch, tmp_path: Path):
    """Controlla che QueryParams venga propagato e che il limite/top-k siano rispettati."""
    seen: dict = {}

    # stub locale di fetch_candidates, con una riga vuota prima per E306
    def stub_fetch_candidates(
        slug: str,
        scope: str,
        limit: int,
        db_path: Path | None,
    ):
        """Cattura i parametri e produce tre candidati con embedding identico."""
        seen.update(slug=slug, scope=scope, limit=limit, db_path=db_path)
        yield {"content": "a", "meta": {}, "embedding": [1.0, 0.0]}
        yield {"content": "b", "meta": {}, "embedding": [1.0, 0.0]}
        yield {"content": "c", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    params = QueryParams(
        db_path=tmp_path / "kb.sqlite",
        slug=DUMMY_SLUG,
        scope="Timmy",
        query="hello",
        k=2,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )
    emb = FakeEmb()

    out = retr.search(params, emb, embedding_model="text-embedding-3-large")

    # embeddings chiamato con la query attesa
    assert emb.calls and emb.calls[-1] == ("hello",)
    assert emb.last_model == "text-embedding-3-large"
    # pass-through di QueryParams verso fetch_candidates
    assert seen == {
        "slug": DUMMY_SLUG,
        "scope": "Timmy",
        "limit": retr.MIN_CANDIDATE_LIMIT,
        "db_path": tmp_path / "kb.sqlite",
    }
    # top-k rispettato e shape dell'output
    assert len(out) == 2
    assert all("content" in r and "score" in r for r in out)


def test_search_accepts_numpy_embeddings(monkeypatch):
    """Compatibilità: client embeddings che ritorna numpy.ndarray (2D)."""
    import numpy as np

    # Stub di fetch_candidates: un solo candidato compatibile
    def stub_fetch_candidates(slug, scope, limit, db_path):  # type: ignore[no-untyped-def]
        yield {"content": "only", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    class NumpyEmb:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
            assert len(texts) == 1
            return np.array([[1.0, 0.0]])

    params = QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query="hello",
        k=1,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )

    out = retr.search(params, NumpyEmb())

    assert len(out) == 1
    assert isinstance(out[0]["score"], float)


def test_search_skips_invalid_candidate_embeddings(monkeypatch):
    """Candidati con embedding vuoto o non numerico vengono ignorati (no crash)."""

    import timmy_kb.cli.retriever as retr

    # 2 validi, 3 invalidi
    def stub_fetch_candidates(slug, scope, limit, db_path):  # type: ignore[no-untyped-def]
        yield {"content": "ok1", "meta": {}, "embedding": [1.0, 0.0]}
        yield {"content": "bad_empty", "meta": {}, "embedding": []}
        yield {"content": "bad_non_numeric", "meta": {}, "embedding": [1.0, "x"]}
        yield {"content": "ok2", "meta": {}, "embedding": [0.0, 1.0]}
        yield {"content": "bad_str", "meta": {}, "embedding": "abc"}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    class Emb:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
            return [[1.0, 0.0]]

    params = QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query="hello",
        k=10,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )

    out = retr.search(params, Emb())

    # solo i due validi
    assert [r["content"] for r in out] == ["ok1", "ok2"]


def test_search_empty_query_embedding_returns_empty(monkeypatch):
    """Se l'embedding della query risulta vuoto, alza un errore esplicito."""

    import timmy_kb.cli.retriever as retr

    def stub_fetch_candidates(slug, scope, limit, db_path):  # type: ignore[no-untyped-def]
        yield {"content": "only", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    class EmptyEmb:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
            return [[]]  # embedding vuoto

    params = QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query="hello",
        k=5,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )

    with pytest.raises(retr.RetrieverError) as exc:
        retr.search(params, EmptyEmb())
    assert getattr(exc.value, "code", None) == retr.ERR_EMBEDDING_INVALID


def test_search_accepts_deque_embedding(monkeypatch):
    """Client che ritorna deque o generatore come singolo vettore."""
    from collections import deque

    import timmy_kb.cli.retriever as retr
    from timmy_kb.cli.retriever import QueryParams

    # Stub di fetch_candidates: un solo candidato compatibile
    def stub_fetch_candidates(slug, scope, limit, db_path):  # type: ignore[no-untyped-def]
        yield {"content": "only", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    class DequeEmb:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
            # Restituisce un vettore come deque (singolo embedding)
            return deque([1.0, 0.0])

    params = QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query="hello",
        k=1,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )

    out = retr.search(params, DequeEmb())

    assert len(out) == 1
    assert isinstance(out[0]["score"], float)


def test_search_accepts_list_of_numpy_arrays(monkeypatch):
    """Client che ritorna list[np.ndarray] come batch (uno vettore)."""
    import numpy as np

    import timmy_kb.cli.retriever as retr
    from timmy_kb.cli.retriever import QueryParams

    def stub_fetch_candidates(slug, scope, limit, db_path):  # type: ignore[no-untyped-def]
        yield {"content": "only", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    class ListNpEmb:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
            assert len(texts) == 1
            return [np.array([1.0, 0.0])]

    params = QueryParams(
        db_path=None,
        slug=DUMMY_SLUG,
        scope="kb",
        query="hello",
        k=1,
        candidate_limit=retr.MIN_CANDIDATE_LIMIT,
    )

    out = retr.search(params, ListNpEmb())

    assert len(out) == 1
    assert isinstance(out[0]["score"], float)
