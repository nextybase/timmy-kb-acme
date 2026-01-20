# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from semantic import vocab_loader as vl


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_to_vocab_invalid_shape_raises() -> None:
    with pytest.raises(ConfigError, match="Canonical vocab shape invalid"):
        vl._to_vocab("invalid")


def test_load_reviewed_vocab_missing_db_raises(tmp_path: Path) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    with pytest.raises(ConfigError, match="tags.db missing or unreadable"):
        vl.load_reviewed_vocab(base, _NoopLogger())
