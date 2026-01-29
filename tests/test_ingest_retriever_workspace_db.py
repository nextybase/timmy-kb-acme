# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest

import timmy_kb.cli.ingest as ingest_mod
from pipeline.file_utils import safe_write_text
from storage.kb_db import fetch_candidates
from storage.kb_store import KbStore
from timmy_kb.cli.ingest import ingest_path
from timmy_kb.cli.retriever import MIN_CANDIDATE_LIMIT, QueryParams, search


class DummyEmbeddingsClient:
    """Stub deterministico che produce embedding numerici semplici."""

    def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            # Vettore lunghezza fissa 8 basato sulla lunghezza del testo (valori finiti e ripetibili)
            base = float(len(text) % 10)
            vectors.append([base + i for i in range(8)])
        return vectors


def _prepare_workspace(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "normalized").mkdir(parents=True, exist_ok=True)
    (base / "book").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    safe_write_text(base / "config" / "config.yaml", "{}\n")
    safe_write_text(base / "book" / "README.md", "# Dummy KB\n")
    safe_write_text(base / "book" / "SUMMARY.md", "* [Intro](intro.md)\n")


def test_ingest_and_search_use_workspace_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "dummy"
    base = tmp_path / f"timmy-kb-{slug}"
    ctx = SimpleNamespace(repo_root_dir=base, slug=slug)
    _prepare_workspace(base)

    store = KbStore.for_slug(slug=slug, repo_root_dir=base)
    db_path = store.effective_db_path()
    assert base / "semantic" in db_path.parents or "semantic" in db_path.parts

    content_path = base / "raw" / "note_ingest.md"
    safe_write_text(content_path, "Questo è un contenuto di prova per Timmy KB.")

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
        context=ctx,
        repo_root_dir=base,
        db_path=db_path,
    )
    assert inserted > 0
    assert db_path.exists()
    assert not (base / "data" / "kb.sqlite").exists()

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


def test_lineage_persisted_in_ingest_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "dummy"
    base = tmp_path / f"timmy-kb-{slug}"
    ctx = SimpleNamespace(repo_root_dir=base, slug=slug)
    _prepare_workspace(base)

    store = KbStore.for_slug(slug=slug, repo_root_dir=base)
    db_path = store.effective_db_path()

    content_path = base / "raw" / "lineage_ingest.md"
    safe_write_text(content_path, "# Title\ncontenuto lineage")

    def _single_chunk(text: str, *, target_tokens: int = 400, overlap_tokens: int = 40) -> list[str]:
        return [text]

    monkeypatch.setattr(ingest_mod, "_chunk_text", _single_chunk, raising=True)

    dummy_embeddings = DummyEmbeddingsClient()
    inserted = ingest_path(
        slug=slug,
        scope="kb",
        path=str(content_path),
        version="v1",
        meta={"slug": slug},
        embeddings_client=dummy_embeddings,
        context=ctx,
        repo_root_dir=base,
        db_path=db_path,
    )
    assert inserted > 0

    candidates = list(fetch_candidates(slug, "kb", limit=5, db_path=db_path))
    assert candidates, "nessun candidato restituito dal DB"
    lineage = candidates[0]["meta"].get("lineage")
    assert isinstance(lineage, dict), "meta.lineage mancante"
    assert lineage.get("source_id")
    assert lineage.get("chunks")
    for chunk_info in lineage["chunks"]:
        expected_keys = {"chunk_index", "chunk_id", "embedding_id"}
        assert expected_keys.issubset(chunk_info.keys())
        assert chunk_info["chunk_id"]
        assert chunk_info["embedding_id"]
