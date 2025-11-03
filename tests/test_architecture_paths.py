# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = [PROJECT_ROOT / "src" / "pipeline", PROJECT_ROOT / "src" / "semantic"]
# Wrapper modules autorizzati a usare open()/write diretti
WHITELIST = {
    PROJECT_ROOT / "src" / "pipeline" / "file_utils.py",
    PROJECT_ROOT / "src" / "pipeline" / "path_utils.py",
}
FORBIDDEN_ATTRS = {"write_text", "write_bytes"}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGET_DIRS:
        for path in target.rglob("*.py"):
            if path in WHITELIST:
                continue
            files.append(path)
    return files


def _collect_violations(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8").replace("\ufeff", "")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - failing parse should break fast
        return [f"{path}: failed to parse ({exc})"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                violations.append(f"{path}:{node.lineno} - direct open() detected")
                continue
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
                violations.append(f"{path}:{node.lineno} - direct Path.{func.attr}() detected")
    return violations


def test_no_unsafe_file_access_in_pipeline_and_semantic():
    violations: list[str] = []
    for file_path in _iter_python_files():
        violations.extend(_collect_violations(file_path))
    assert not violations, "\n".join(["Unsafe file access detected:"] + violations)
