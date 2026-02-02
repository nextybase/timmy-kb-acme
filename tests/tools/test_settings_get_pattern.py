# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_no_dotted_settings_get_usage() -> None:
    pattern = re.compile(r"settings\.get\(\s*(?:\"[^\"\n]*\.[^\"\n]*\"|'[^'\n]*\.[^'\n]*')")
    violations: list[str] = []
    for path in Path("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            violations.append(str(path))
    if violations:
        pytest.fail(
            "Found dotted `settings.get()` calls. "
            "Use `_get_config_value` or explicit nested traversal instead:\n"
            + "\n".join(violations)
        )
