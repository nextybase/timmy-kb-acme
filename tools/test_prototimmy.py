# SPDX-License-Identifier: GPL-3.0-only
# tools/test_prototimmy.py
from __future__ import annotations

import sys
from pathlib import Path

from ai.check import run_prototimmy_dummy_check
from pipeline.exceptions import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    _ = argv  # placeholder per eventuali argomenti futuri
    try:
        result = run_prototimmy_dummy_check()
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - diagnostico
        print(f"[ERRORE] Test protoTimmy fallito: {exc}")
        return 1

    print("✓ protoTimmy raggiungibile")
    print("✓ Planner Assistant raggiungibile")
    print("✓ OCP Executor raggiungibile")
    if result.get("steps"):
        print("\n=== Dettaglio catena ===")
        for step in result["steps"]:
            role = step.get("role", "")
            model = step.get("model", "")
            print(f"- {role}: model={model}")
    if result.get("ok"):
        print("\n✓ Giro completo protoTimmy -> Planner -> OCP OK")
        return 0
    print("\n[ERRORE] Catena non completata")
    if result.get("error"):
        print(f" Dettaglio: {result['error']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
