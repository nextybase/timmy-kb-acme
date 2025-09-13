#!/usr/bin/env python3
"""
Esegue QA locale in modo "safe":
- black --check <PATHS> (se installato)
- flake8 <PATHS> (se installato)
- mypy --config-file mypy.ini (se installato)
Opzionale: --with-tests per eseguire anche pytest.

Note:
- I PATHS sono allineati alla allowlist usata da mypy.ini (sezione "files=").
- mypy viene eseguito SENZA argomenti posizionali, così rispetta mypy.ini.

Exit code:
- 0 se tutti i tool presenti sono passati o assenti (skip)
- 1 se uno dei tool presenti fallisce
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import List, Sequence, Tuple

# Stessi path di mypy.ini -> files=
LINT_PATHS: Sequence[str] = (
    "src/config_ui",
    "src/pipeline/drive",
    "src/pipeline/drive_utils.py",
)


def run_if_available(name: str, args: List[str]) -> Tuple[str, int | None]:
    """Esegue 'args' solo se 'name' è risolvibile nel PATH; altrimenti skip."""
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
        # Black/Flake8 solo sui path allowlistati (coerenti con mypy.ini)
        ("black", ["black", "--check", *LINT_PATHS]),
        ("flake8", ["flake8", *LINT_PATHS]),
        # IMPORTANT: niente argomenti posizionali a mypy -> userà mypy.ini (files=)
        ("mypy", ["mypy", "--config-file", "mypy.ini"]),
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
