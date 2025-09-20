#!/usr/bin/env python3
"""
Esegue QA locale in modo "safe":
- isort --check-only <PATHS> (se installato)
- black --check <PATHS> (se installato)
- ruff check <PATHS> (se installato)
- mypy --config-file mypy.ini (se installato)
Opzionale: --with-tests per eseguire anche pytest.

Note:
- I PATHS sono allineati ai target standard del progetto (src/ e tests/).
- Tutti i tool vengono invocati come moduli di Python (python -m ...)
  per evitare dipendenze da PATH o wrapper eseguibili su Windows.

Exit code:
- 0 se tutti i tool presenti sono passati o assenti (skip)
- 1 se uno dei tool presenti fallisce
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from typing import List, Sequence, Tuple

# Percorsi standard per linting e formattazione
LINT_PATHS: Sequence[str] = (
    "src",
    "tests",
)


def run_module_if_available(module: str, args: List[str]) -> Tuple[str, int | None]:
    """Esegue `python -m <module> <args>` se il modulo è importabile; altrimenti skip."""
    if importlib.util.find_spec(module) is None:
        print(f"[qa-safe] {module} non installato: skip")
        return module, None
    cmd = [sys.executable, "-m", module, *args]
    print(f"[qa-safe] Eseguo: {' '.join(cmd)}")
    proc = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    return module, int(proc.returncode)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-tests", action="store_true", help="Esegui anche pytest")
    args = ap.parse_args(argv)

    failures: List[str] = []

    checks: List[Tuple[str, List[str]]] = [
        ("isort", ["--check-only", "--profile=black", *LINT_PATHS]),
        ("black", ["--check", *LINT_PATHS]),
        ("ruff", ["check", *LINT_PATHS]),
        ("mypy", ["--config-file", "mypy.ini"]),
    ]
    if args.with_tests:
        checks.append(("pytest", ["-ra"]))

    for module, module_args in checks:
        _, rc = run_module_if_available(module, module_args)
        if rc is not None and rc != 0:
            failures.append(module)

    if failures:
        print(f"[qa-safe] Falliti: {', '.join(failures)}")
        return 1
    print("[qa-safe] OK")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
