from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.logging_utils import get_structured_logger
from semantic.vocab_loader import load_reviewed_vocab


def _mk_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "kb"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def test_load_vocab_missing_db_returns_empty_and_logs(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    base = _mk_workspace(tmp_path)
    logger = get_structured_logger("test.vocab.missing")

    vocab = load_reviewed_vocab(base, logger)

    assert vocab == {}
    out = capsys.readouterr().out
    assert "semantic.vocab.db_missing" in out
    assert f"slug={base.name}" in out


def test_load_vocab_empty_db_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    base = _mk_workspace(tmp_path)
    db = base / "semantic" / "tags.db"
    db.write_bytes(b"")

    import semantic.vocab_loader as vl

    monkeypatch.setattr(vl, "load_tags_reviewed_db", lambda p: {}, raising=True)

    logger = get_structured_logger("test.vocab.empty")
    vocab = load_reviewed_vocab(base, logger)

    assert vocab == {}
    out = capsys.readouterr().out
    assert "semantic.vocab.db_empty" in out
    assert f"slug={base.name}" in out


def test_load_vocab_valid_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    base = _mk_workspace(tmp_path)
    db = base / "semantic" / "tags.db"
    db.write_bytes(b"sqlite placeholder")

    data = {
        "tags": [
            {"name": "finance", "action": "keep", "synonyms": ["finanza"]},
            {"name": "fatturato", "action": "merge_into:finance", "synonyms": ["revenues"]},
        ]
    }
    import semantic.vocab_loader as vl

    monkeypatch.setattr(vl, "load_tags_reviewed_db", lambda p: data, raising=True)

    logger = get_structured_logger("test.vocab.ok")
    vocab = load_reviewed_vocab(base, logger)

    assert "finance" in vocab and "aliases" in vocab["finance"]
    out = capsys.readouterr().out
    assert "semantic.vocab.loaded" in out
    assert f"slug={base.name}" in out
