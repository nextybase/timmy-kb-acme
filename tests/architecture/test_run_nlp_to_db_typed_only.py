# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_KWARGS = {
    "rebuild",
    "only_missing",
    "max_workers",
    "worker_batch_size",
    "enable_entities",
}


def _iter_python_files() -> list[Path]:
    roots = [Path("src"), Path("tests")]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob("*.py"))
    return files


def test_run_nlp_to_db_uses_typed_options_only() -> None:
    violations: list[str] = []
    for path in _iter_python_files():
        rel = path.as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn_name = None
            if isinstance(node.func, ast.Name):
                fn_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fn_name = node.func.attr
            if fn_name != "run_nlp_to_db":
                continue
            found = sorted(kw.arg for kw in node.keywords if kw.arg is not None and kw.arg in FORBIDDEN_KWARGS)
            if found:
                violations.append(f"{rel}:{node.lineno} forbidden_kwargs={found}")

    assert not violations, "run_nlp_to_db must use typed options only:\n" + "\n".join(violations)
