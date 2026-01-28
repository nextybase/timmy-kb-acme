# SPDX-License-Identifier: GPL-3.0-only
# tests/test_vocab_loader_integration_db.py
from __future__ import annotations

import json
from pathlib import Path

import semantic.vocab_loader as vl


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_loads_reviewed_vocab_json(tmp_path: Path):
    base = tmp_path / "output" / "timmy-kb-dummy"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)

    reviewed = sem / "reviewed_vocab.json"
    reviewed.write_text(json.dumps({"canon": {"aliases": ["alias1", "alias2"]}}), encoding="utf-8")

    vocab = vl.load_reviewed_vocab(base, _NoopLogger())
    assert "canon" in vocab
    assert "aliases" in vocab["canon"]
    assert vocab["canon"]["aliases"] == ["alias1", "alias2"]
