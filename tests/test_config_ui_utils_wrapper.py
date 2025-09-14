from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from src.config_ui.utils import ensure_within_and_resolve


def test_wrapper_resolves_within_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    f = base / "x.txt"
    f.write_text("ok", encoding="utf-8")

    out = ensure_within_and_resolve(base, f)
    assert out == f.resolve()


def test_wrapper_blocks_outside_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    with pytest.raises(ConfigError):
        _ = ensure_within_and_resolve(base, outside)
