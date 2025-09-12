#!/usr/bin/env python3
"""
Esegue QA locale in modo "safe":
- black --check src tests (se installato)
- flake8 src tests (se installato)
- mypy src (se installato)
Opzionale: --with-tests per eseguire anche pytest.

Exit code:
- 0 se tutti i tool presenti sono passati o assenti (skip)
- 1 se uno dei tool presenti fallisce
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import List, Tuple


def run_if_available(name: str, args: List[str]) -> Tuple[str, int | None]:
    if shutil.which(name) is None:
        print(f"[qa-safe] {name} non installato: skip")
        return name, None
    print(f"[qa-safe] Eseguo: {' '.join(args)}")
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr)
    return name, int(proc.returncode)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-tests", action="store_true", help="Esegui anche pytest")
    args = ap.parse_args(argv)

    failures: List[str] = []
    checks: List[Tuple[str, List[str]]] = [
        ("black", ["black", "--check", "src", "tests"]),
        ("flake8", ["flake8", "src", "tests"]),
        ("mypy", ["mypy", "src"]),
    ]
    if args.with_tests:
        checks.append(("pytest", ["pytest", "-ra"]))

    for name, cmd in checks:
        _, rc = run_if_available(name, cmd)
        if rc is not None and rc != 0:
            failures.append(name)

    if failures:
        print(f"[qa-safe] Falliti: {', '.join(failures)}")
        return 1
    print("[qa-safe] OK")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
