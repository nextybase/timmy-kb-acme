# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import vocab_loader as vl
from tests._helpers.workspace_paths import local_workspace_dir


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_to_vocab_invalid_shape_raises() -> None:
    with pytest.raises(ConfigError, match="Canonical vocab shape invalid"):
        vl._to_vocab("invalid")


def test_load_reviewed_vocab_missing_db_raises(tmp_path: Path) -> None:
    base = local_workspace_dir(tmp_path / "output", "dummy")
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError, match="tags.db missing or unreadable"):
        vl.load_reviewed_vocab(base, _NoopLogger(), slug="dummy")


def test_to_vocab_case_conflict_merges_aliases() -> None:
    data = {
        "tags": [
            {"name": "Roma", "synonyms": ["Italian capital"]},
            {"name": "roma", "synonyms": ["capital"]},
        ]
    }
    vocab = vl._to_vocab(data)
    assert "Roma" in vocab
    assert vocab["Roma"]["aliases"] == ["Italian capital", "capital"]


def test_to_vocab_alias_collision_is_deterministic() -> None:
    data = {
        "tags": [
            {"name": "Alpha", "synonyms": ["shared"]},
            {"name": "Beta", "synonyms": ["shared"]},
        ]
    }
    vocab = vl._to_vocab(data)
    assert set(vocab) == {"Alpha", "Beta"}
    assert vocab["Alpha"]["aliases"] == ["shared"]
    assert vocab["Beta"]["aliases"] == ["shared"]


def test_to_vocab_merge_loop_is_deterministic() -> None:
    data = {
        "tags": [
            {"name": "Alpha", "action": "merge_into:Beta", "synonyms": ["a"]},
            {"name": "Beta", "action": "merge_into:Alpha", "synonyms": ["b"]},
        ]
    }
    vocab = vl._to_vocab(data)
    assert set(vocab) == {"Alpha", "Beta"}
    assert set(vocab["Alpha"]["aliases"]) >= {"Beta", "b"}
    assert set(vocab["Beta"]["aliases"]) >= {"Alpha", "a"}
