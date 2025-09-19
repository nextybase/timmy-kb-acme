#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"open\(.*\)\.write\(")


def main() -> int:
    root = Path.cwd()
    bad: list[str] = []
    for p in root.rglob("*.py"):
        # Escludi virtualenv e cache
        if any(
            part in {".git", ".venv", "venv", "__pycache__", "tools", "scripts"} for part in p.parts
        ):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if PATTERN.search(txt):
            bad.append(str(p))
    if bad:
        print("Use safe_write_* al posto di open().write(...) in:")
        for b in bad:
            print(" -", b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
