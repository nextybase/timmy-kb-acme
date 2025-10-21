# tests/test_vocab_loader_failfast.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import timmykb.semantic.vocab_loader as vl
from pipeline.exceptions import ConfigError


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_returns_empty_when_db_missing(tmp_path: Path):
    base = tmp_path / "output" / "timmy-kb-acme"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)

    vocab = vl.load_reviewed_vocab(base, _NoopLogger())
    assert vocab == {}


def test_raises_configerror_on_db_open_failure(tmp_path: Path, monkeypatch: Any):
    base = tmp_path / "output" / "timmy-kb-acme"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    db = sem / "tags.db"
    db.write_bytes(b"not a real sqlite db")  # file presente ma corrotto

    # Forza sqlite3.connect a fallire per verificare il fail-fast
    import sqlite3

    def _boom(*_a, **_k):
        raise sqlite3.OperationalError("db is malformed")

    monkeypatch.setattr("sqlite3.connect", _boom, raising=True)

    with pytest.raises(ConfigError) as ei:
        _ = vl.load_reviewed_vocab(base, _NoopLogger())

    err = ei.value
    assert getattr(err, "file_path", None) == db


def test_path_guard_is_enforced(tmp_path: Path, monkeypatch: Any):
    base = tmp_path / "output" / "timmy-kb-acme"
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    # ensure_within_and_resolve che fallisce per simulare path traversal/symlink malevolo
    def _unsafe(*_a, **_k):
        raise ConfigError("unsafe path", file_path=str(base / "semantic"))

    monkeypatch.setattr("pipeline.path_utils.ensure_within_and_resolve", _unsafe, raising=True)

    with pytest.raises(ConfigError):
        _ = vl.load_reviewed_vocab(base, _NoopLogger())
