#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter

Blocca YAML con segreti inline in config/ (usato da pre-commit e CI)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List

SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|secret|token|password)", re.IGNORECASE)
SECRET_VALUE_PATTERN = re.compile(r"(sk-|xox|ghp)", re.IGNORECASE)
YAML_KEY_PATTERN = re.compile(r"^\s*([A-Za-z0-9_-]+):\s*(.*)$")


def _iter_files(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_file():
            yield path


def _check_file(path: Path) -> List[str]:
    violations: List[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # pragma: no cover - error handled as violation
        violations.append(f"{path}: unable to read file ({exc})")
        return violations

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = YAML_KEY_PATTERN.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        key_lower = key.lower()
        if key_lower.endswith("_env"):
            continue
        if SECRET_KEY_PATTERN.search(key):
            violations.append(f"{path}:{idx}: key '{key}' looks like a secret (use *_env indirection)")
            continue
        if value and SECRET_VALUE_PATTERN.search(value):
            violations.append(
                f"{path}:{idx}: inline value '{value.strip()}' looks like a secret (use *_env indirection)"
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail if config YAMLs contain inline secrets.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="YAML files to inspect (defaults to config/*.yaml, config/*.yml when omitted).",
    )
    args = parser.parse_args(argv)

    targets = list(args.paths)
    if not targets:
        targets = [str(p) for p in Path("config").glob("*.y*ml")]

    violations: List[str] = []
    for file_path in _iter_files(targets):
        if file_path.suffix.lower() not in {".yml", ".yaml"}:
            continue
        violations.extend(_check_file(file_path))

    if violations:
        sys.stderr.write(
            "Detected potential secrets in config YAMLs. " "Move secrets to .env and reference them via *_env keys.\n"
        )
        for msg in violations:
            sys.stderr.write(f"  - {msg}\n")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
