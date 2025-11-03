# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import timmykb.retriever as retr
from timmykb.retriever import QueryParams


class FakeEmb:
    def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Sequence[Sequence[float]]:
        # Vettore unitario sull'asse X
        return [[1.0, 0.0]]


def _mk_stub_candidates(contents: list[str], scores: list[float]):
    assert len(contents) == len(scores)

    def _gen(project_slug: str, scope: str, limit: int, db_path: Path | None):
        for c, s in zip(contents, scores, strict=False):
            # embedding normalizzato per avere coseno = s
            s = float(s)
            t = max(0.0, 1.0 - s * s)
            emb = [s, math.sqrt(t)]
            yield {"content": c, "meta": {}, "embedding": emb}

    return _gen


def test_topk_k_zero(monkeypatch, tmp_path: Path):
    contents = ["a", "b", "c"]
    scores = [0.9, 0.8, 0.7]
    monkeypatch.setattr(retr, "fetch_candidates", _mk_stub_candidates(contents, scores))
    out = retr.search(
        QueryParams(tmp_path / "kb.sqlite", "p", "s", "q", k=0, candidate_limit=retr.MIN_CANDIDATE_LIMIT),
        FakeEmb(),
    )
    assert out == []


def test_topk_small_k_with_ties_stable(monkeypatch, tmp_path: Path):
    # punteggi: due top con pari score, l'ordine deve rispettare l'ordine di arrivo (a poi b)
    contents = ["a", "b", "c", "d"]
    scores = [0.9, 0.9, 0.5, 0.4]
    monkeypatch.setattr(retr, "fetch_candidates", _mk_stub_candidates(contents, scores))
    out = retr.search(
        QueryParams(tmp_path / "kb.sqlite", "p", "s", "q", k=2, candidate_limit=retr.MIN_CANDIDATE_LIMIT),
        FakeEmb(),
    )
    assert [r["content"] for r in out] == ["a", "b"]
    assert all(out[i]["score"] >= out[i + 1]["score"] for i in range(len(out) - 1))


def test_topk_k_one(monkeypatch, tmp_path: Path):
    contents = ["a", "b", "c"]
    scores = [0.6, 0.95, 0.7]
    monkeypatch.setattr(retr, "fetch_candidates", _mk_stub_candidates(contents, scores))
    out = retr.search(
        QueryParams(tmp_path / "kb.sqlite", "p", "s", "q", k=1, candidate_limit=retr.MIN_CANDIDATE_LIMIT),
        FakeEmb(),
    )
    assert len(out) == 1 and out[0]["content"] == "b"


def test_topk_k_ge_n_behaves_like_full_sort(monkeypatch, tmp_path: Path):
    contents = ["a", "b", "c"]
    scores = [0.8, 0.8, 0.9]
    monkeypatch.setattr(retr, "fetch_candidates", _mk_stub_candidates(contents, scores))
    params = QueryParams(tmp_path / "kb.sqlite", "p", "s", "q", k=10, candidate_limit=retr.MIN_CANDIDATE_LIMIT)
    out = retr.search(params, FakeEmb())
    # ordinamento completo: c (0.9), a (0.8), b (0.8). a prima di b per stabilità
    assert [r["content"] for r in out] == ["c", "a", "b"]
