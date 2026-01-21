# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest

import timmy_kb.cli.ingest as ing


class _SpyEmb:
    instances = 0

    def __init__(self) -> None:
        type(self).instances += 1

    def embed_texts(self, texts: Sequence[str], *, model: str | None = None):  # type: ignore[override]
        return [[0.1] for _ in texts]


def _prepare_workspace(tmp_path: Path, *, slug: str) -> tuple[Path, SimpleNamespace]:
    base = tmp_path / f"kb-{slug}"
    raw_dir = base / "raw"
    book_dir = base / "book"
    semantic_dir = base / "semantic"
    logs_dir = base / "logs"
    config_dir = base / "config"
    raw_dir.mkdir(parents=True, exist_ok=True)
    book_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (book_dir / "README.md").write_text("# README\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    ctx = SimpleNamespace(repo_root_dir=base, slug=slug)
    return base, ctx


@pytest.fixture(autouse=True)
def _isolate_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "kb-root"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))


def test_ingest_folder_reuses_single_embeddings_instance(monkeypatch, tmp_path: Path):
    base, ctx = _prepare_workspace(tmp_path, slug="p")
    root = base / "raw"
    # Prepara due file piccoli (1 chunk ciascuno)
    f1 = root / "a.md"
    f2 = root / "b.md"
    f1.write_text("Hello A", encoding="utf-8")
    f2.write_text("Hello B", encoding="utf-8")

    # Sostituisci OpenAIEmbeddings con uno spy senza toccare l'API
    monkeypatch.setattr(ing, "OpenAIEmbeddings", _SpyEmb)
    _SpyEmb.instances = 0
    summary = ing.ingest_folder(
        slug="p",
        scope="s",
        folder_glob=str(root / "*.md"),
        version="v1",
        meta={},
        embeddings_client=None,
        context=ctx,
    )

    assert _SpyEmb.instances == 1, "Il client embeddings deve essere istanziato una sola volta"
    assert summary == {"files": 2, "chunks": 2}


def test_ingest_folder_short_circuit_on_empty(monkeypatch, tmp_path: Path):
    # Cartella vuota → nessuna istanziazione
    monkeypatch.setattr(ing, "OpenAIEmbeddings", _SpyEmb)
    _SpyEmb.instances = 0
    base, ctx = _prepare_workspace(tmp_path, slug="p")
    root = base / "raw"

    summary = ing.ingest_folder(
        slug="p",
        scope="s",
        folder_glob=str(root / "*.md"),
        version="v1",
        meta={},
        embeddings_client=None,
        context=ctx,
    )
    assert summary == {"files": 0, "chunks": 0}
    assert _SpyEmb.instances == 0
