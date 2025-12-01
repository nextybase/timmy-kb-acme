#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tool rapido per validare lo schema VisionOutput e confermare la presenza dei log
"response_format" attesi.

Usalo da repo root:
  pip install -r requirements-dev.txt    # se serve
  python scripts/verify_vision_schema.py --schema schemas/VisionOutput.schema.json
  python scripts/verify_vision_schema.py --logs output/timmy-kb-*/logs/onboarding.log
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


def check_schema(schema_path: Path) -> None:
    print(f"[schema] carico {schema_path}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"schema non trovato: {schema_path}") from exc
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    missing = props - required
    extra = required - props
    if missing:
        raise RuntimeError(f"mancano in required: {', '.join(sorted(missing))}")
    if extra:
        raise RuntimeError(f"required contiene chiavi non presenti: {', '.join(sorted(extra))}")
    print(f"[schema] ok ({len(props)} properties, required allineato)")


def scan_logs(pattern: str, files: Iterable[Path]) -> None:
    matcher = re.compile(pattern)
    for log_path in files:
        if not log_path.exists():
            continue
        print(f"[log] esamino {log_path}")
        for idx, line in enumerate(log_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if matcher.search(line):
                start = max(0, idx - 2)
                tail = line
                print(f"\n== match {log_path}:{idx} ==")
                print(f"{start+1:05d}: {tail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica schema VisionOutput e log response_format")
    parser.add_argument("--schema", type=Path, help="Path allo schema JSON da validare")
    parser.add_argument("--logs", nargs="+", type=Path, help="Glob (via PowerShell) dei log da scansionare")
    parser.add_argument(
        "--pattern",
        default=r"semantic\.vision\.response_format(_payload)?",
        help="Pattern regex per le righe da estrarre",
    )
    args = parser.parse_args()

    if args.schema:
        check_schema(args.schema)

    if args.logs:
        scan_logs(args.pattern, args.logs)

    if not args.schema and not args.logs:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
