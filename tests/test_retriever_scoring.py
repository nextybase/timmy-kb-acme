# tests/test_retriever_scoring.py
from __future__ import annotations

from typing import Sequence

import numpy as np

import src.retriever as r
from src.retriever import QueryParams, search


class EmbedOne:
    """Stub compatibile con il Protocol EmbeddingsClient: accetta `model` kw e
    ritorna una lista di vettori float per ciascun testo.
    """

    def __init__(self, vec: list[float]) -> None:
        self.vec = vec

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        return [list(self.vec) for _ in texts]


def _cand(content: str, emb: list[float], meta: dict | None = None) -> dict:
    return {"content": content, "embedding": emb, "meta": meta or {}}


def test_search_scoring_and_tie_break_deterministic(monkeypatch) -> None:
    # query embedding punta (1,0)
    embeddings = EmbedOne([1.0, 0.0])

    # Tre candidati: due con score identico (=1.0), uno peggiore (=0.0)
    cands = [
        _cand("A", [1.0, 0.0]),  # idx 0, score 1.0
        _cand("B", [1.0, 0.0]),  # idx 1, score 1.0  (tie con A → A prima di B)
        _cand("C", [0.0, 1.0]),  # idx 2, score 0.0
    ]

    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: cands)

    # k >= n → ordina tutto; atteso: A, B, C
    params_all = QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="q",
        k=10,
        candidate_limit=r.MIN_CANDIDATE_LIMIT,
    )
    out_all = search(params_all, embeddings)
    assert [x["content"] for x in out_all] == ["A", "B", "C"]

    # k < n (branch nlargest) → atteso: A, B
    params_top2 = QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="q",
        k=2,
        candidate_limit=r.MIN_CANDIDATE_LIMIT,
    )
    out_top2 = search(params_top2, embeddings)
    assert [x["content"] for x in out_top2] == ["A", "B"]


def test_search_accepts_nested_numpy_embedding(monkeypatch) -> None:
    embeddings = EmbedOne([1.0, 0.0, 0.0])
    # embedding annidato: [np.array([...])]
    nested = [np.array([1.0, 0.0, 0.0], dtype=float)]
    cands = [
        _cand("nested-ok", nested),
        _cand("worse", [0.0, 1.0, 0.0]),
    ]

    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: cands)

    params = QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="q",
        k=1,
        candidate_limit=r.MIN_CANDIDATE_LIMIT,
    )
    out = search(params, embeddings)
    assert [x["content"] for x in out] == ["nested-ok"]


def test_search_handles_missing_embeddings_field(monkeypatch) -> None:
    embeddings = EmbedOne([1.0, 0.0])
    cands = [
        {"content": "no-emb", "meta": {}},  # embedding mancante → trattato come []
        _cand("ok", [1.0, 0.0]),
    ]

    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: cands)

    params = QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="q",
        k=2,
        candidate_limit=r.MIN_CANDIDATE_LIMIT,
    )
    out = search(params, embeddings)
    # "ok" deve venire prima di "no-emb" (score 1.0 vs 0.0)
    assert [x["content"] for x in out] == ["ok", "no-emb"]


def test_search_large_vectors_preserve_order(monkeypatch) -> None:
    size = 20000
    base_vec = [float((i % 17) - 8) for i in range(size)]
    embeddings = EmbedOne(base_vec)

    slightly_worse = [v + (0.25 if (i % 2 == 0) else -0.25) for i, v in enumerate(base_vec)]
    orthogonal_like = [0.0 for _ in range(size)]

    cands = [
        _cand("best", list(base_vec)),
        _cand("slightly-worse", slightly_worse),
        _cand("orth", orthogonal_like),
    ]

    monkeypatch.setattr(r, "fetch_candidates", lambda *a, **k: cands)

    params = QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="q",
        k=3,
        candidate_limit=r.MIN_CANDIDATE_LIMIT,
    )
    out = search(params, embeddings)

    contents = [x["content"] for x in out]
    assert contents == ["best", "slightly-worse", "orth"]
    assert out[0]["score"] >= out[1]["score"] > out[2]["score"]
