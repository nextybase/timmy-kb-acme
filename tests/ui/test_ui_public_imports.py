# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import ast
from pathlib import Path


def _collect_private_backend_imports(path: Path) -> list[str]:
    offenders: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith(("pipeline", "semantic")):
                for alias in node.names:
                    if alias.name.startswith("_"):
                        offenders.append(f"{path}: from {mod} import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name or ""
                parts = name.split(".")
                if parts and parts[0] in {"pipeline", "semantic"} and any(p.startswith("_") for p in parts[1:]):
                    offenders.append(f"{path}: import {name}")
    return offenders


def test_ui_imports_use_only_public_backend_symbols() -> None:
    """Garantisce che i moduli UI non importino simboli privati di pipeline/semantic."""

    ui_root = Path(__file__).resolve().parents[2] / "src" / "ui"
    roots = [ui_root / "pages", ui_root / "services"]
    offenders: list[str] = []

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            offenders.extend(_collect_private_backend_imports(path))

    assert not offenders, "Import privati backend rilevati" + "\n".join(offenders)
