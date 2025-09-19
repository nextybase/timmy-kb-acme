from __future__ import annotations

from pathlib import Path
from typing import Sequence

import src.ingest as ingest


class FakeEmb:
    def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Sequence[Sequence[float]]:
        return [[0.0] * 3 for _ in texts]


def test_ingest_rejects_outside_base(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "note.txt"
    outside.write_text("hello", encoding="utf-8")

    # Evita I/O DB
    monkeypatch.setattr(ingest, "insert_chunks", lambda **kwargs: 0)

    n = ingest.ingest_path(
        project_slug="p",
        scope="s",
        path=str(outside),
        version="v",
        meta={},
        embeddings_client=FakeEmb(),
        base_dir=base,
    )
    assert n == 0


def test_ingest_within_base_succeeds(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    f = base / "ok.txt"
    f.write_text("uno due tre quattro cinque", encoding="utf-8")

    # Stub insert_chunks per contare i chunk
    called = {}

    def _stub_insert_chunks(**kwargs):
        called["chunks"] = list(kwargs.get("chunks") or [])
        return len(called["chunks"]) if called.get("chunks") else 0

    monkeypatch.setattr(ingest, "insert_chunks", _stub_insert_chunks)

    n = ingest.ingest_path(
        project_slug="p",
        scope="s",
        path=str(f),
        version="v",
        meta={},
        embeddings_client=FakeEmb(),
        base_dir=base,
    )
    assert n == len(called["chunks"]) and n > 0
