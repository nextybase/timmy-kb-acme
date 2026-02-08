# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.contract


def test_semantic_vision_log_is_write_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    allowlist = {repo_root / "src" / "semantic" / "vision_provision.py"}
    hits: list[str] = []
    for candidate in (repo_root / "src").rglob("*.py"):
        if "semantic.vision.log" not in candidate.read_text(encoding="utf-8"):
            continue
        if candidate.resolve() in allowlist:
            continue
        hits.append(str(candidate.relative_to(repo_root)))
    assert (
        not hits
    ), f"Il log `semantic.vision.log` è riservato al producer _write_audit_line; trovati riferimenti runtime in: {hits}"
