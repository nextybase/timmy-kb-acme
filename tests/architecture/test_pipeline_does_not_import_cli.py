# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ast
from pathlib import Path

PIPELINE_ROOT = Path("src/pipeline")
FORBIDDEN_PREFIX = "timmy_kb.cli"


def _collect_forbidden_imports(source: str, path: Path) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FORBIDDEN_PREFIX or alias.name.startswith(FORBIDDEN_PREFIX + "."):
                    forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == FORBIDDEN_PREFIX or module.startswith(FORBIDDEN_PREFIX + "."):
                forbidden.append(module)
    return forbidden


def test_pipeline_does_not_import_cli_modules() -> None:
    violations: list[str] = []
    if not PIPELINE_ROOT.exists():
        return

    for path in PIPELINE_ROOT.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        forbidden = _collect_forbidden_imports(source, path)
        for imp in forbidden:
            violations.append(
                f"{path}: imports '{imp}' (pipeline must not depend on timmy_kb.cli; use runtime services/APIs)"
            )

    assert not violations, "\n".join(violations)
