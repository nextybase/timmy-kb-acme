# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from semantic.vocab_loader import load_reviewed_vocab


def _mk_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "kb"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def test_load_vocab_missing_reviewed_json_raises(tmp_path: Path):
    base = _mk_workspace(tmp_path)
    logger = get_structured_logger("test.vocab.missing")

    with pytest.raises(ConfigError, match="tags.db missing or unreadable"):
        load_reviewed_vocab(base, logger)


def test_load_vocab_invalid_json_type_raises(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    base = _mk_workspace(tmp_path)
    reviewed_path = base / "semantic" / "reviewed_vocab.json"
    reviewed_path.write_text("[]", encoding="utf-8")

    logger = get_structured_logger("test.vocab.invalid")
    caplog.clear()
    caplog.set_level(logging.INFO)
    with pytest.raises(ConfigError, match="reviewed vocab invalid type"):
        load_reviewed_vocab(base, logger)
    assert any(rec.getMessage() == "semantic.vocab.review_invalid_type" for rec in caplog.records)


def test_load_vocab_valid_json_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    base = _mk_workspace(tmp_path)
    reviewed_path = base / "semantic" / "reviewed_vocab.json"
    reviewed_path.write_text(json.dumps({"analytics": {"aliases": ["alias"]}}), encoding="utf-8")

    logger = get_structured_logger("test.vocab.ok")
    caplog.clear()
    caplog.set_level(logging.INFO)
    vocab = load_reviewed_vocab(base, logger)

    assert "analytics" in vocab and vocab["analytics"]["aliases"] == ["alias"]
