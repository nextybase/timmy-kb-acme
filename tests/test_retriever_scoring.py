# tests/test_retriever_scoring.py
from __future__ import annotations

from typing import Sequence

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
