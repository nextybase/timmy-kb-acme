# SPDX-License-Identifier: GPL-3.0-or-later
"""Verifica che src/ non importi nulla da tools/."""

from __future__ import annotations

import ast
from pathlib import Path


def _normalize(module: str | None) -> str:
    return module or ""


def test_src_does_not_import_tools_modules() -> None:
    errors: list[str] = []
    src_root = Path("src")
    for path in src_root.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _normalize(alias.name)
                    if mod == "tools" or mod.startswith("tools."):
                        errors.append(f"{path}:{mod} importa da tools/")
            elif isinstance(node, ast.ImportFrom):
                module = _normalize(node.module)
                if module == "tools" or module.startswith("tools."):
                    errors.append(f"{path}:{module} importa da tools/")
    assert not errors, "\n".join(errors)
