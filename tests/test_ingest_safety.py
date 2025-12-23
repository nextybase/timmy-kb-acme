# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pytest

import ingest as ingest
from pipeline.exceptions import ConfigError


class FakeEmb:
    def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Sequence[Sequence[float]]:
        return [[0.0] * 3 for _ in texts]


@pytest.fixture(autouse=True)
def _isolate_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path / "kb-root"))


def test_ingest_rejects_outside_base(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "note.txt"
    outside.write_text("hello", encoding="utf-8")

    # Evita I/O DB
    monkeypatch.setattr(ingest, "insert_chunks", lambda **kwargs: 0)

    n = ingest.ingest_path(
        slug="p",
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
        slug="p",
        scope="s",
        path=str(f),
        version="v",
        meta={"slug": "dummy"},
        embeddings_client=FakeEmb(),
        base_dir=base,
    )
    assert n > 0


def test_ingest_path_requires_base_dir(monkeypatch, tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("ciao", encoding="utf-8")
    monkeypatch.setattr(ingest, "insert_chunks", lambda **kwargs: 0)
    with pytest.raises(ConfigError):
        ingest.ingest_path(
            slug="p",
            scope="s",
            path=str(f),
            version="v",
            meta={},
            embeddings_client=FakeEmb(),
        )


def test_ingest_folder_infers_base_dir(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    f = root / "keep.txt"
    f.write_text("ciao mondo", encoding="utf-8")

    captured: dict[str, Any] = {"base": None, "paths": []}

    def _fake_ingest_path(*, path: str, base_dir: Path, **kwargs) -> int:
        captured["base"] = Path(base_dir)
        captured["paths"].append(path)
        return 1

    monkeypatch.setattr(ingest, "ingest_path", _fake_ingest_path)

    summary = ingest.ingest_folder(
        slug="slug",
        scope="scope",
        folder_glob=str(root / "**" / "*.txt"),
        version="v1",
        meta={},
        embeddings_client=FakeEmb(),
    )

    assert summary == {"files": 1, "chunks": 1}
    assert captured["base"] == root.resolve()
    assert captured["paths"] == [str(f)]


def test_ingest_folder_bubbles_unexpected_errors(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    (root / "boom.txt").write_text("bad", encoding="utf-8")

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest, "ingest_path", _boom)

    with pytest.raises(RuntimeError):
        ingest.ingest_folder(
            slug="slug",
            scope="scope",
            folder_glob=str(root / "*.txt"),
            version="v1",
            meta={},
            embeddings_client=FakeEmb(),
        )


def test_ingest_folder_skips_config_error(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    ok = root / "ok.txt"
    skip = root / "skip.txt"
    ok.write_text("ciao", encoding="utf-8")
    skip.write_text("ciao", encoding="utf-8")

    def _ingest(**kwargs):
        if kwargs["path"].endswith("skip.txt"):
            raise ConfigError("bad encoding")
        return 2

    monkeypatch.setattr(ingest, "ingest_path", _ingest)

    summary = ingest.ingest_folder(
        slug="slug",
        scope="scope",
        folder_glob=str(root / "*.txt"),
        version="v1",
        meta={},
        embeddings_client=FakeEmb(),
    )

    assert summary == {"files": 1, "chunks": 2}


def test_ingest_within_base_calls_insert(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    f = base / "ok.txt"
    f.write_text("uno due tre quattro cinque", encoding="utf-8")

    called = {}

    def _stub_insert_chunks(**kwargs):
        called["chunks"] = list(kwargs.get("chunks") or [])
        return len(called["chunks"])

    monkeypatch.setattr(ingest, "insert_chunks", _stub_insert_chunks)
    n = ingest.ingest_path(
        slug="p",
        scope="s",
        path=str(f),
        version="v",
        meta={"slug": "dummy"},
        embeddings_client=FakeEmb(),
        base_dir=base,
    )
    assert n == len(called["chunks"]) and n > 0


def test_ingest_folder_respects_max_files(monkeypatch, tmp_path: Path) -> None:
    for idx in range(3):
        f = tmp_path / f"file_{idx}.md"
        f.write_text(f"content {idx}", encoding="utf-8")

    processed: list[str] = []

    def _stub_ingest_path(*, path: str, **kwargs: Any) -> int:
        processed.append(Path(path).name)
        return 1

    monkeypatch.setattr(ingest, "ingest_path", _stub_ingest_path)

    summary = ingest.ingest_folder(
        slug="slug",
        scope="scope",
        folder_glob=str(tmp_path / "*.md"),
        version="v1",
        meta={"slug": "dummy"},
        embeddings_client=FakeEmb(),
        max_files=2,
    )

    assert summary == {"files": 2, "chunks": 2}
    assert len(processed) == 2


def test_ingest_folder_honors_batch_size(monkeypatch, tmp_path: Path) -> None:
    files = []
    for idx in range(5):
        f = tmp_path / f"doc_{idx}.md"
        f.write_text("ciao", encoding="utf-8")
        files.append(f.name)

    processed: list[str] = []

    def _stub_ingest_path(*, path: str, **kwargs: Any) -> int:
        processed.append(Path(path).name)
        return 1

    monkeypatch.setattr(ingest, "ingest_path", _stub_ingest_path)

    summary = ingest.ingest_folder(
        slug="slug",
        scope="scope",
        folder_glob=str(tmp_path / "*.md"),
        version="v1",
        meta={},
        embeddings_client=FakeEmb(),
        batch_size=2,
    )

    assert summary == {"files": 5, "chunks": 5}
    assert sorted(processed) == sorted(files)
