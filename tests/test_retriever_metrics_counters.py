# SPDX-License-Identifier: GPL-3.0-only
# tests/test_retriever_metrics_counters.py
import logging

import timmy_kb.cli.retriever as retr


class _EmbClient:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        return [[0.2, 0.8]]  # embedding query


def _params():
    return retr.QueryParams(
        db_path=None,
        slug="proj",
        scope="kb",
        query="hello",
        k=4,
        candidate_limit=500,  # range valido [500, 20000]
    )


def test_retriever_metrics_coerce_and_skip(monkeypatch, caplog):
    cands = [
        {"content": "short", "meta": {}, "embedding": [0.3, 0.7]},  # short-circuit
        {"content": "norm", "meta": {}, "embedding": [[0.2, 0.8]]},  # normalize
        {"content": "skip_invalid", "meta": {}, "embedding": ["x", "y"]},  # skipped
        {"content": "none_vec", "meta": {}, "embedding": None},  # [], score=0
    ]
    monkeypatch.setattr(retr, "fetch_candidates", lambda *a, **k: list(cands))

    caplog.set_level(logging.INFO)
    out = retr.search(_params(), _EmbClient())

    ids = [x["content"] for x in out]
    assert "skip_invalid" not in ids
    assert set(ids).issubset({"short", "norm", "none_vec"})

    rec = next((r for r in caplog.records if r.getMessage() == "retriever.metrics"), None)
    assert rec is not None
    coerce = getattr(rec, "coerce", {})
    assert coerce.get("short") == 1
    assert coerce.get("normalized") == 1
    assert coerce.get("skipped") == 1

    scores = {x["content"]: x["score"] for x in out}
    assert scores.get("none_vec", 0.0) == 0.0
    assert scores.get("short", 0.0) > 0.0
    assert scores.get("norm", 0.0) > 0.0
