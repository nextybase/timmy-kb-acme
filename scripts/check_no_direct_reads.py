#!/usr/bin/env python3
"""
Blocca utilizzi di lettura non sicuri nei moduli pipeline/* e semantic/*:
- open(..., "r"/"rb"/"r+") o Path.open("r"/"rb"/"r+")
- Path.read_text(...)

Eccezione ergonomica: consentiti `.read_text(...)` e `.open("r", ...)` su variabili
il cui nome inizia con `safe_` (pattern usato nel repo dopo ensure_within_and_resolve).

Uso:
  python scripts/check_no_direct_reads.py [file_or_dir ...]
Se non vengono passati argomenti, scansiona `src/pipeline` e `src/semantic`.
Exit code 1 se trova violazioni.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

READ_MODES = {"r", "rb", "r+", "rt"}


def _iter_py_files(paths: Iterable[Path]) -> Iterable[Path]:
    for p in paths:
        if p.is_dir():
            yield from (q for q in p.rglob("*.py") if q.is_file())
        elif p.suffix == ".py" and p.is_file():
            yield p


def _get_mode_from_call(call: ast.Call) -> str | None:
    # Positional second arg
    if (
        len(call.args) >= 2
        and isinstance(call.args[1], ast.Constant)
        and isinstance(call.args[1].value, str)
    ):
        return call.args[1].value
    # Keyword arg 'mode'
    for kw in call.keywords or []:
        if (
            kw.arg == "mode"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def _is_safe_receiver(node: ast.AST) -> bool:
    # Consenti nomi che iniziano con safe_
    return isinstance(node, ast.Name) and node.id.startswith("safe_")


def check_file(path: Path) -> List[Tuple[int, int, str]]:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(txt, filename=str(path))
    except SyntaxError:
        return []
    issues: List[Tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Builtin open(...)
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = _get_mode_from_call(node)
                if mode and any(m in mode for m in READ_MODES):
                    issues.append(
                        (
                            node.lineno,
                            node.col_offset,
                            "open() in lettura vietato: usa ensure_within_and_resolve + Path.open",
                        )
                    )
            # Path-like .open("r", ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "open":
                if _is_safe_receiver(node.func.value):
                    continue
                mode = _get_mode_from_call(node)
                if mode and any(m in mode for m in READ_MODES):
                    issues.append(
                        (
                            node.lineno,
                            node.col_offset,
                            ".open('r') in lettura vietato su path non safe_*",
                        )
                    )
            # .read_text(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "read_text":
                if _is_safe_receiver(node.func.value):
                    continue
                issues.append(
                    (
                        node.lineno,
                        node.col_offset,
                        ".read_text() vietato su path non safe_*",
                    )
                )

    return issues


def main(argv: List[str]) -> int:
    args = (
        [Path(a) for a in argv]
        if argv
        else [Path("src/pipeline"), Path("src/semantic"), Path("src/adapters")]
    )
    files = list(_iter_py_files(args))
    exit_code = 0
    for f in files:
        # limitiamo solo a pipeline/* e semantic/*
        try:
            rel = f.as_posix()
        except Exception:
            rel = str(f)
        if not (
            "src/pipeline/" in rel or "src/semantic/" in rel or "src/adapters/" in rel
        ):
            continue
        issues = check_file(f)
        for ln, col, msg in issues:
            print(f"{f}:{ln}:{col}: {msg}")
        if issues:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
