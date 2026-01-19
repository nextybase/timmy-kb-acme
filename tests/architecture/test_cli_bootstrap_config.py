# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import ast
from pathlib import Path


def _has_bootstrap_config(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == "bootstrap_config":
            return True
    return False


def _iter_client_context_load_calls(tree: ast.AST) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "load":
            if isinstance(func.value, ast.Name) and func.value.id == "ClientContext":
                calls.append(node)
    return calls


def test_cli_explicit_bootstrap_config() -> None:
    cli_root = Path("src/timmy_kb/cli")
    missing: list[str] = []

    for path in cli_root.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            lineno = exc.lineno or 0
            offset = exc.offset or 0
            raise AssertionError(f"CLI non parsabile: {path}:{lineno}:{offset}") from exc
        for call in _iter_client_context_load_calls(tree):
            if not _has_bootstrap_config(call):
                lineno = getattr(call, "lineno", 1)
                missing.append(f"{path}:{lineno}")
                break

    assert not missing, f"bootstrap_config mancante in CLI: {sorted(set(missing))}"
