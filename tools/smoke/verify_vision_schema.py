#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tool rapido per validare lo schema VisionOutput e confermare la presenza dei log
"response_format" attesi.

Usalo da repo root:
  pip install -r requirements-dev.txt    # se serve
  python tools/verify_vision_schema.py --schema src/ai/schemas/VisionOutput.schema.json
  python tools/verify_vision_schema.py --logs output/timmy-kb-*/logs/onboarding.log
"""

from __future__ import annotations

import argparse
import json
import re
from glob import glob
from pathlib import Path
from typing import Iterable, Sequence


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


def expand_pattern(path: Path) -> Sequence[Path]:
    text = str(path)
    if "*" in text or "?" in text or "[" in text:
        return [Path(p) for p in glob(text)]
    return [path]


def scan_logs(pattern: str, files: Iterable[Path]) -> None:
    matcher = re.compile(pattern)
    found = False
    for log_path in files:
        if not log_path.exists():
            print(f"[log] file mancante: {log_path}")
            continue
        print(f"[log] esamino {log_path}")
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, start=1):
            if matcher.search(line):
                found = True
                start = max(0, idx - 2)
                end = min(len(lines), idx + 2)
                snippet = "\n".join(f"{ln:05d}: {lines[ln-1]}" for ln in range(start + 1, end + 1))
                print(f"\n== match {log_path}:{idx} ==\n{snippet}")
    if not found:
        print("[log] pattern non trovato in nessun file analizzato.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica schema VisionOutput e log response_format")
    parser.add_argument("--schema", type=Path, help="Path allo schema JSON da validare")
    parser.add_argument("--logs", nargs="+", type=Path, help="Percorsi o glob espliciti dei log da scansionare")
    parser.add_argument(
        "--scan-dirs",
        nargs="+",
        type=Path,
        default=[Path("output"), Path(".timmykb/logs")],
        help="Directory da esplorare automaticamente (cerco *.log)",
    )
    parser.add_argument(
        "--pattern",
        default=r"semantic\.vision\.response_format(_payload)?",
        help="Pattern regex per le righe da estrarre",
    )
    args = parser.parse_args()

    if args.schema:
        check_schema(args.schema)

    log_paths: list[Path] = []
    if args.logs:
        for entry in args.logs:
            log_paths.extend(expand_pattern(entry))
    if args.scan_dirs:
        for base_dir in args.scan_dirs:
            if not base_dir.exists():
                continue
            for match in glob(str(base_dir / "*.log")):
                log_paths.append(Path(match))

    if log_paths:
        scan_logs(args.pattern, log_paths)
    elif not args.schema:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
