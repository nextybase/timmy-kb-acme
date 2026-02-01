# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

TARGET_DIRS = ("src/timmy_kb/cli", "src/api")
FORBIDDEN_PREFIXES = ("ui", "ui.pages", "ui.services")


def _iter_python_files(directories: Iterable[str]) -> Iterable[Path]:
    for directory in directories:
        root = Path(directory)
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            yield path


def _collect_forbidden_imports(source: str, path: Path) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in FORBIDDEN_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    forbidden.append(module)
    return forbidden


def test_dev_channel_does_not_import_ui() -> None:
    violations: list[str] = []
    for path in _iter_python_files(TARGET_DIRS):
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        forbidden = _collect_forbidden_imports(source, path)
        for imp in forbidden:
            violations.append(f"{path}: imports '{imp}' (Dev channel must stay away from ui.*; use a facade)")
    assert not violations, "\n".join(violations)
