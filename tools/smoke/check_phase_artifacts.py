# SPDX-License-Identifier: GPL-3.0-only
"""
DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter

Soft check: avvisa se alcune fasi risultano con artifacts=0.

Uso:
  python -m tools.smoke.check_phase_artifacts --json out/bench.json

Exit code sempre 0 (non-gating); stampa WARNING su stdout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}")


def _check_bench_json(data: Dict[str, Any]) -> None:
    arts = data.get("semantic_index_artifacts") or {}
    if isinstance(arts, dict):
        for size, cases in arts.items():
            if not isinstance(cases, dict):
                continue
            for name, val in cases.items():
                try:
                    iv = int(val)
                except Exception:
                    continue
                if iv == 0:
                    _warn(f"semantic_index_markdown_to_db[{size}].{name}: artifacts=0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_path", default="out/bench.json")
    args = ap.parse_args()

    p = Path(args.json_path)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(data, dict):
        _check_bench_json(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
