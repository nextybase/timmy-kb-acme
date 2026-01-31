# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

import semantic.vocab_loader as vl
from pipeline.exceptions import ConfigError


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def _mk_semantic_db_placeholder(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)
    db = sem / "tags.db"
    db.write_bytes(b"sqlite placeholder")
    return base


def test_load_reviewed_vocab_unreadable_db(tmp_path: Path) -> None:
    base = _mk_semantic_db_placeholder(tmp_path)

    with pytest.raises(ConfigError, match="tags.db missing or unreadable") as ei:
        _ = vl.load_reviewed_vocab(base, _NoopLogger())

    err = ei.value
    assert getattr(err, "file_path", None) == str(base / "semantic" / "tags.db")
