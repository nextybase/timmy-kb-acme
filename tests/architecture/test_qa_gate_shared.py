# SPDX-License-Identifier: GPL-3.0-only
"""Guardrail: UI e CLI usano la stessa precondizione QA gate."""

from __future__ import annotations

import ast
from pathlib import Path


def _has_call(path: Path, name: str) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def test_ui_and_core_share_qa_gate_precondition() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    ui_path = repo_root / "src/ui/pages/semantics.py"
    core_path = repo_root / "src/semantic/frontmatter_service.py"
    assert _has_call(ui_path, "require_qa_gate_pass"), "UI must use require_qa_gate_pass"
    assert _has_call(core_path, "require_qa_gate_pass"), "Core must use require_qa_gate_pass"
