from __future__ import annotations

from pathlib import Path

import pytest

import timmykb.semantic.vocab_loader as vl
from pipeline.exceptions import ConfigError


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def _mk_semantic_db_placeholder(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-acme"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    db = sem / "tags.db"
    db.write_bytes(b"sqlite placeholder")
    return base


def test_raises_configerror_on_query_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = _mk_semantic_db_placeholder(tmp_path)
    db = base / "semantic" / "tags.db"

    import sqlite3

    # Simula errore a livello di query/cursor nel loader reale
    def _boom(_path: str):
        raise sqlite3.OperationalError("malformed database or query failed")

    monkeypatch.setattr(vl, "_load_tags_reviewed", _boom, raising=True)

    with pytest.raises(ConfigError) as ei:
        _ = vl.load_reviewed_vocab(base, _NoopLogger())

    err = ei.value
    assert getattr(err, "file_path", None) == db
