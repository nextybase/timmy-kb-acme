#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

SPDX_TOKEN = "SPDX-License-Identifier"  # noqa: S105 - SPDX marker, non-segreto

def has_spdx_header(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            head = [next(fh, "") for _ in range(8)]
        return any(SPDX_TOKEN in (line or "") for line in head)
    except Exception:
        return False

def main(argv: list[str]) -> int:
    files = [Path(p) for p in argv if p.endswith(".py")]
    missing = []
    for f in files:
        # limita a sorgenti del repo
        if not any(str(f).startswith(p) for p in ("src/", "tests/", "scripts/")):
            continue
        if not has_spdx_header(f):
            missing.append(f)
    if missing:
        sys.stderr.write(
            "Missing SPDX header in:\n" + "\n".join(f"  - {m}" for m in missing) + "\n"
        )
        sys.stderr.write(
            f'Add a line near the top, e.g.: "# {SPDX_TOKEN}: GPL-3.0-only"\n'
        )
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
