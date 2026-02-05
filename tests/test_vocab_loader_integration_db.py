# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_vocab_loader_integration_db.py
from __future__ import annotations

from pathlib import Path

from tests._helpers.workspace_paths import local_workspace_dir

import semantic.vocab_loader as vl
from storage.tags_store import save_tags_reviewed


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_loads_reviewed_vocab_from_db(tmp_path: Path):
    base = local_workspace_dir(tmp_path / "output", "dummy")
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)

    db_path = sem / "tags.db"
    save_tags_reviewed(
        str(db_path),
        {
            "version": "2",
            "reviewed_at": "2024-01-01T00:00:00",
            "keep_only_listed": False,
            "tags": [
                {
                    "name": "canon",
                    "action": "keep",
                    "synonyms": ["alias1", "alias2"],
                    "note": "",
                }
            ],
        },
    )

    vocab = vl.load_reviewed_vocab(base, _NoopLogger())
    assert "canon" in vocab
    assert "aliases" in vocab["canon"]
    assert vocab["canon"]["aliases"] == ["alias1", "alias2"]
