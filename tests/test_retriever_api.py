from __future__ import annotations

"""
Tests for retriever.search API.

Verifica:
- pass-through dei parametri via QueryParams verso fetch_candidates
- compatibilità con EmbeddingsClient (protocollo) e top-k
"""

from pathlib import Path
from typing import Sequence

import src.retriever as retr
from src.retriever import QueryParams


class FakeEmb:
    """Finto client embeddings conforme al protocollo (firma con argomento keyword-only `model`)."""

    def __init__(self) -> None:
        self.calls: list[Sequence[str]] = []

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> Sequence[Sequence[float]]:
        """Ritorna un embedding unitario e registra le chiamate per l'asserzione."""
        self.calls.append(tuple(texts))
        return [[1.0, 0.0]]


def test_search_uses_query_params_and_limit(monkeypatch, tmp_path: Path):
    """Controlla che QueryParams venga propagato e che il limite/top-k siano rispettati."""
    seen: dict = {}

    # stub locale di fetch_candidates, con una riga vuota prima per E306
    def stub_fetch_candidates(
        project_slug: str,
        scope: str,
        limit: int,
        db_path: Path | None,
    ):
        """Cattura i parametri e produce tre candidati con embedding identico."""
        seen.update(project_slug=project_slug, scope=scope, limit=limit, db_path=db_path)
        yield {"content": "a", "meta": {}, "embedding": [1.0, 0.0]}
        yield {"content": "b", "meta": {}, "embedding": [1.0, 0.0]}
        yield {"content": "c", "meta": {}, "embedding": [1.0, 0.0]}

    monkeypatch.setattr(retr, "fetch_candidates", stub_fetch_candidates)

    params = QueryParams(
        db_path=tmp_path / "kb.sqlite",
        project_slug="acme",
        scope="Timmy",
        query="hello",
        k=2,
        candidate_limit=5,
    )
    emb = FakeEmb()

    out = retr.search(params, emb)

    # embeddings chiamato con la query attesa
    assert emb.calls and emb.calls[-1] == ("hello",)
    # pass-through di QueryParams verso fetch_candidates
    assert seen == {
        "project_slug": "acme",
        "scope": "Timmy",
        "limit": 5,
        "db_path": tmp_path / "kb.sqlite",
    }
    # top-k rispettato e shape dell'output
    assert len(out) == 2
    assert all("content" in r and "score" in r for r in out)
