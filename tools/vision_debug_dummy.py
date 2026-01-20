# SPDX-License-Identifier: GPL-3.0-only
# tools/vision_debug_dummy.py
from __future__ import annotations

import sys
from pathlib import Path

from pipeline.exceptions import ConfigError
from tools.ai_checks import run_vision_dummy_check

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    slug = args[0] if args else "dummy"

    try:
        result = run_vision_dummy_check(workspace_slug=slug)
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - diagnostico
        print(f"[ERRORE] Vision debug fallito: {exc}")
        return 1

    print("=== Vision debug ===")
    print(f"slug: {result['slug']}")
    print(f"model: {result['model']}")
    print(f"use_kb: {result.get('use_kb')}")
    print(f"strict_output: {result.get('strict_output')}")
    print(f"mapping: {result.get('mapping_path')}")
    print(f"cartelle_raw: {result.get('cartelle_raw_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
