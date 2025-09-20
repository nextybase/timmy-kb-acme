from __future__ import annotations

from pathlib import Path
from typing import Sequence

import src.ingest as ing


class _SpyEmb:
    instances = 0

    def __init__(self) -> None:
        type(self).instances += 1

    def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
        return [[0.1] for _ in texts]


def test_ingest_folder_reuses_single_embeddings_instance(monkeypatch, tmp_path: Path):
    # Prepara due file piccoli (1 chunk ciascuno)
    f1 = tmp_path / "a.md"
    f2 = tmp_path / "b.md"
    f1.write_text("Hello A", encoding="utf-8")
    f2.write_text("Hello B", encoding="utf-8")

    # Sostituisci OpenAIEmbeddings con uno spy senza toccare l'API
    monkeypatch.setattr(ing, "OpenAIEmbeddings", _SpyEmb)
    _SpyEmb.instances = 0

    summary = ing.ingest_folder(
        project_slug="p",
        scope="s",
        folder_glob=str(tmp_path / "*.md"),
        version="v1",
        meta={},
        embeddings_client=None,
    )

    assert _SpyEmb.instances == 1, "Il client embeddings deve essere istanziato una sola volta"
    assert summary == {"files": 2, "chunks": 2}


def test_ingest_folder_short_circuit_on_empty(monkeypatch, tmp_path: Path):
    # Cartella vuota → nessuna istanziazione
    monkeypatch.setattr(ing, "OpenAIEmbeddings", _SpyEmb)
    _SpyEmb.instances = 0

    summary = ing.ingest_folder(
        project_slug="p",
        scope="s",
        folder_glob=str(tmp_path / "*.md"),
        version="v1",
        meta={},
        embeddings_client=None,
    )
    assert summary == {"files": 0, "chunks": 0}
    assert _SpyEmb.instances == 0
