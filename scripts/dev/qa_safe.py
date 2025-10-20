#!/usr/bin/env python3
"""
Esegue QA locale in modo "safe" (auto-rimeditivo) con una smoke suite:
1) isort (write-mode)        → riordina import
2) black (write-mode)        → format definitivo
3) ruff check --fix          → lint + fix non distruttivi
4) mypy                      → type-check mirato (solo su target esistenti)
5) pytest                    → smoke ui/retriever/smoke

Exit code:
- 0 se tutto ok o tool assenti (skip)
- 1 se uno qualsiasi step fallisce
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

# Percorsi standard per linting e formattazione
LINT_PATHS: Sequence[str] = ("src", "tests")


def run(cmd: List[str]) -> int:
    print(f"[qa-safe] Eseguo: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    return int(proc.returncode)


def run_module_if_available(module: str, args: List[str]) -> Tuple[str, int | None]:
    """
    Esegue `python -m <module> <args>` se il modulo è importabile; altrimenti skip.
    Ritorna (nome_modulo, rc | None).
    """
    if importlib.util.find_spec(module) is None:
        print(f"[qa-safe] {module} non installato: skip", flush=True)
        return module, None
    rc = run([sys.executable, "-m", module, *args])
    return module, rc


def _existing_targets(candidates: Sequence[str]) -> List[str]:
    out: List[str] = []
    for c in candidates:
        p = Path(c)
        if p.exists():
            out.append(str(p))
    return out


def main(argv: List[str] | None = None) -> int:
    failures: List[str] = []

    # 1) isort (write-mode)
    mod, rc = run_module_if_available("isort", ["--profile=black", "--line-length=120", *LINT_PATHS])
    if rc not in (0, None):
        failures.append(mod)

    # 2) black (write-mode)
    mod, rc = run_module_if_available("black", [*LINT_PATHS])
    if rc not in (0, None):
        failures.append(mod)

    # 3) ruff (lint + fix non-distruttivo)
    mod, rc = run_module_if_available("ruff", ["check", *LINT_PATHS, "--fix"])
    if rc not in (0, None):
        failures.append(mod)

    # 4) mypy (solo su target esistenti)
    mypy_candidates = ["src/config_ui/", "src/pipeline/drive/", "src/pipeline/drive_utils.py"]
    mypy_targets = _existing_targets(mypy_candidates)
    if mypy_targets:
        mod, rc = run_module_if_available("mypy", ["--config-file", "mypy.ini", *mypy_targets])
        if rc not in (0, None):
            failures.append(mod)
    else:
        print("[qa-safe] mypy: nessun target esistente tra " f"{mypy_candidates} → skip", flush=True)

    # 5) pytest (smoke UI/retriever)
    smoke_targets = ["tests/ui", "tests/retriever", "tests/smoke"]
    existing_smoke = _existing_targets(smoke_targets)
    if existing_smoke:
        mod, rc = run_module_if_available("pytest", ["-q", *existing_smoke])
        if rc not in (0, None):
            failures.append(mod)
    else:
        print(f"[qa-safe] pytest: nessun target esistente tra {smoke_targets} → skip", flush=True)

    if failures:
        print(f"[qa-safe] Falliti: {', '.join(failures)}", flush=True)
        return 1

    print("[qa-safe] OK", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
