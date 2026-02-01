# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from semantic.vocab_loader import load_reviewed_vocab
from storage.tags_store import save_tags_reviewed


def _mk_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "kb"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def test_load_vocab_missing_db_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    base = _mk_workspace(tmp_path)
    logger = get_structured_logger("test.vocab.missing")

    caplog.clear()
    caplog.set_level(logging.INFO)
    with pytest.raises(ConfigError, match="tags.db missing or unreadable"):
        load_reviewed_vocab(base, logger)
    assert any(rec.getMessage() == "semantic.vocab.db_missing" for rec in caplog.records)


def test_load_vocab_valid_db_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    base = _mk_workspace(tmp_path)
    db_path = base / "semantic" / "tags.db"
    save_tags_reviewed(
        str(db_path),
        {
            "version": "2",
            "reviewed_at": "2024-01-01T00:00:00",
            "keep_only_listed": False,
            "tags": [
                {"name": "analytics", "action": "keep", "synonyms": ["alias"], "note": ""},
            ],
        },
    )

    logger = get_structured_logger("test.vocab.invalid")
    caplog.clear()
    caplog.set_level(logging.INFO)
    vocab = load_reviewed_vocab(base, logger)
    assert vocab["analytics"]["aliases"] == ["alias"]
    assert any(rec.getMessage() == "semantic.vocab.loaded" for rec in caplog.records)
