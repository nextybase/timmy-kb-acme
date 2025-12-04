# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

import ingest as ingest_mod
from ingest import ingest_path
from kb_db import DEFAULT_DB_PATH
from retriever import MIN_CANDIDATE_LIMIT, QueryParams, search
from storage.kb_store import KbStore


class DummyEmbeddingsClient:
    """Stub deterministico che produce embedding numerici semplici."""

    def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            # Vettore lunghezza fissa 8 basato sulla lunghezza del testo (valori finiti e ripetibili)
            base = float(len(text) % 10)
            vectors.append([base + i for i in range(8)])
        return vectors


def test_ingest_and_search_use_workspace_db(dummy_workspace: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    base: Path = dummy_workspace["base"]
    slug: str = dummy_workspace["slug"]

    store = KbStore.for_slug(slug=slug, base_dir=base)
    db_path = store.effective_db_path()
    assert base / "semantic" in db_path.parents or "semantic" in db_path.parts

    content_path = base / "raw" / "note_ingest.md"
    content_path.write_text("Questo è un contenuto di prova per Timmy KB.", encoding="utf-8")

    def _no_chunk(text: str, *, target_tokens: int = 400, overlap_tokens: int = 40) -> list[str]:
        return [text]

    monkeypatch.setattr(ingest_mod, "_chunk_text", _no_chunk, raising=True)

    dummy_embeddings = DummyEmbeddingsClient()
    inserted = ingest_path(
        slug=slug,
        scope="kb",
        path=str(content_path),
        version="v1",
        meta={"slug": slug},
        embeddings_client=dummy_embeddings,
        base_dir=base,
        db_path=db_path,
    )
    assert inserted > 0
    assert db_path.exists()
    assert not DEFAULT_DB_PATH.exists()

    params = QueryParams(
        db_path=db_path,
        slug=slug,
        scope="kb",
        query="Timmy KB",
        k=1,
        candidate_limit=MIN_CANDIDATE_LIMIT,
    )
    results = search(params, dummy_embeddings)
    assert results
    assert "Timmy KB" in (results[0].get("content") or "")
    assert results[0].get("meta", {}).get("slug") == slug
