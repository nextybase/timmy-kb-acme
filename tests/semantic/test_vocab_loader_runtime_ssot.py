# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import builtins
import logging
from pathlib import Path
from typing import Any, Callable, cast

import pytest

from semantic import api as semantic_api
from semantic import vocab_loader
from storage.tags_store import save_tags_reviewed


def _mk_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "kb"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def _write_valid_tags_db(base: Path) -> None:
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


@pytest.mark.parametrize(
    "loader",
    [
        vocab_loader.load_reviewed_vocab,
        semantic_api.load_reviewed_vocab,
    ],
)
def test_runtime_ssot_load_reviewed_vocab_does_not_read_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: Callable[..., dict[str, dict[str, list[str]]]],
) -> None:
    base = _mk_workspace(tmp_path)
    _write_valid_tags_db(base)
    (base / "semantic" / "tags_reviewed.yaml").write_text("tags: []\n", encoding="utf-8")

    real_open = builtins.open
    real_read_text = Path.read_text

    def _guard_open(file: Any, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        try:
            p = Path(file)
        except Exception:
            return real_open(file, *args, **kwargs)
        if p.name == "tags_reviewed.yaml":
            raise AssertionError("Runtime SSoT must not read semantic/tags_reviewed.yaml")
        return real_open(file, *args, **kwargs)

    def _guard_read_text(path_self: Path, *args: Any, **kwargs: Any) -> str:
        if path_self.name == "tags_reviewed.yaml":
            raise AssertionError("Runtime SSoT must not read semantic/tags_reviewed.yaml")
        return cast(str, real_read_text(path_self, *args, **kwargs))

    monkeypatch.setattr(builtins, "open", _guard_open)
    monkeypatch.setattr(Path, "read_text", _guard_read_text)

    logger = logging.getLogger("test.runtime.ssot")
    vocab = loader(base, logger, slug="dummy")
    assert vocab["analytics"]["aliases"] == ["alias"]
