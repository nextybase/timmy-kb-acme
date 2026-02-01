# SPDX-License-Identifier: GPL-3.0-or-later
# tools/kg_debug_dummy.py

from __future__ import annotations

import sys
from pathlib import Path

from pipeline.exceptions import ConfigError
from tools.ai_checks import run_kgraph_dummy_check

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    slug = args[0] if args else "dummy"

    try:
        result = run_kgraph_dummy_check(workspace_slug=slug)
    except ConfigError as exc:
        print(f"[ERRORE CONFIG] {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - diagnostico
        print(f"[ERRORE] KG debug fallito: {exc}")
        return 1

    print("=== KG debug dummy ===")
    print(f"slug: {result['slug']}")
    print(f"tag count: {result.get('tags_count')}")
    print(f"relations count: {result.get('relations_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
