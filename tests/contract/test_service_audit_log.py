# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.contract
def test_semantic_vision_log_is_write_only() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    matches: list[Path] = []
    for path in (repository_root / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "semantic.vision.log" in text:
            matches.append(path)
    expected = repository_root / "src" / "semantic" / "vision_provision.py"
    assert matches == [expected]
