# tests/test_retriever_ranking_invariance_short_circuit.py
import logging

import timmykb.retriever as retr


class _EmbClient:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        return [[0.5, 0.5]]  # embedding query


def _params():
    return retr.QueryParams(
        db_path=None,
        project_slug="proj",
        scope="kb",
        query="hello world",
        k=4,
        candidate_limit=500,  # range valido [500, 20000]
    )


def test_ranking_invariance_between_short_circuit_and_normalize(monkeypatch, caplog):
    # Scenario A: embedding piatti -> short-circuit
    cands_short = [
        {"content": "A", "meta": {"id": "A"}, "embedding": [1.0, 0.0]},
        {"content": "B", "meta": {"id": "B"}, "embedding": [0.0, 1.0]},
        {"content": "C", "meta": {"id": "C"}, "embedding": [0.9, 0.1]},
        {"content": "D", "meta": {"id": "D"}, "embedding": [0.1, 0.9]},
    ]
    # Scenario B: stesse direzioni ma formato che forza normalize_embeddings
    cands_norm = [
        {"content": "A", "meta": {"id": "A"}, "embedding": [[1.0, 0.0]]},
        {"content": "B", "meta": {"id": "B"}, "embedding": [[0.0, 1.0]]},
        {"content": "C", "meta": {"id": "C"}, "embedding": [[0.9, 0.1]]},
        {"content": "D", "meta": {"id": "D"}, "embedding": [[0.1, 0.9]]},
    ]

    params = _params()
    emb = _EmbClient()

    # Run A (short-circuit)
    monkeypatch.setattr(retr, "fetch_candidates", lambda *a, **k: list(cands_short))
    caplog.set_level(logging.INFO)
    out_short = retr.search(params, emb)
    rec_a = next((r for r in caplog.records if r.getMessage() == "retriever.metrics"), None)
    assert rec_a is not None
    assert getattr(rec_a, "coerce", {}).get("short") == 4
    assert getattr(rec_a, "coerce", {}).get("normalized") == 0
    assert getattr(rec_a, "coerce", {}).get("skipped") == 0

    # Run B (normalize)
    caplog.clear()
    monkeypatch.setattr(retr, "fetch_candidates", lambda *a, **k: list(cands_norm))
    out_norm = retr.search(params, emb)
    rec_b = next((r for r in caplog.records if r.getMessage() == "retriever.metrics"), None)
    assert rec_b is not None
    assert getattr(rec_b, "coerce", {}).get("short") == 0
    assert getattr(rec_b, "coerce", {}).get("normalized") == 4
    assert getattr(rec_b, "coerce", {}).get("skipped") == 0

    # Invarianza: stesso ordine e stessi score (entro epsilon)
    eps = 1e-9
    assert [x["content"] for x in out_short] == [x["content"] for x in out_norm]
    for a, b in zip(out_short, out_norm, strict=True):
        assert abs(a["score"] - b["score"]) <= eps
