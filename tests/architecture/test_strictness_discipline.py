# SPDX-License-Identifier: GPL-3.0-or-later
"""Guardrail: strict=False e cache TTL non ammessi nei percorsi core."""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIRS = (
    Path("src/pipeline"),
    Path("src/semantic"),
    Path("src/timmy_kb/cli"),
    Path("src/storage"),
)


def _iter_core_files() -> list[Path]:
    files: list[Path] = []
    for root in CORE_DIRS:
        if not root.exists():
            continue
        files.extend(root.rglob("*.py"))
    return files


def _is_call_to(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False


def _kw_value(call: ast.Call, key: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def _is_const_bool(node: ast.AST | None, value: bool) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


def _report(path: Path, node: ast.AST, message: str) -> str:
    lineno = getattr(node, "lineno", "?")
    return f"{path}:{lineno} {message}"


def test_core_disallows_sanitize_filename_non_strict():
    errors: list[str] = []
    for path in _iter_core_files():
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not _is_call_to(node, "sanitize_filename"):
                continue
            call = node
            strict_value = _kw_value(call, "strict")
            if strict_value is not None:
                errors.append(_report(path, call, "sanitize_filename strict kw is not allowed in core"))
            allow_fallback = _kw_value(call, "allow_fallback")
            if allow_fallback is not None:
                errors.append(_report(path, call, "sanitize_filename allow_fallback kw is not allowed in core"))
    assert not errors, "\n".join(errors)


def test_core_disallows_iter_safe_pdfs_cache():
    errors: list[str] = []
    for path in _iter_core_files():
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not _is_call_to(node, "iter_safe_pdfs"):
                continue
            call = node
            use_cache = _kw_value(call, "use_cache")
            if use_cache is not None and not _is_const_bool(use_cache, False):
                errors.append(_report(path, call, "iter_safe_pdfs use_cache must be False in core"))
    assert not errors, "\n".join(errors)
