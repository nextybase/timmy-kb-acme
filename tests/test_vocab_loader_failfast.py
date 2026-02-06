# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_vocab_loader_failfast.py
from __future__ import annotations

from pathlib import Path

import pytest

import semantic.vocab_loader as vl
from pipeline.exceptions import ConfigError
from tests._helpers.workspace_paths import local_workspace_dir


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_returns_empty_when_db_missing(tmp_path: Path):
    base = local_workspace_dir(tmp_path / "output", "dummy")
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError, match="tags.db missing or unreadable"):
        _ = vl.load_reviewed_vocab(base, _NoopLogger(), slug="dummy")


def test_reviewed_vocab_json_is_ignored_when_db_missing(tmp_path: Path):
    base = local_workspace_dir(tmp_path / "output", "dummy")
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    reviewed_path = sem / "reviewed_vocab.json"
    reviewed_path.write_text('{"canon": {"aliases": ["alias"]}}', encoding="utf-8")

    with pytest.raises(ConfigError, match="tags.db missing or unreadable") as ei:
        _ = vl.load_reviewed_vocab(base, _NoopLogger(), slug="dummy")

    err = ei.value
    assert getattr(err, "file_path", None) == str(sem / "tags.db")


def test_path_guard_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = local_workspace_dir(tmp_path / "output", "dummy")
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    # ensure_within_and_resolve che fallisce per simulare path traversal/symlink malevolo
    def _unsafe(*_a, **_k):
        raise ConfigError("unsafe path", file_path=str(base / "semantic"))

    monkeypatch.setattr("pipeline.path_utils.ensure_within_and_resolve", _unsafe, raising=True)

    with pytest.raises(ConfigError):
        _ = vl.load_reviewed_vocab(base, _NoopLogger(), slug="dummy")
