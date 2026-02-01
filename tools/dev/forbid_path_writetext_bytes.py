# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN = (".write_text(", ".write_bytes(")


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for arg in argv:
        p = Path(arg)
        try:
            if p.suffix != ".py":
                continue
            rel = p.as_posix()
            if not rel.startswith("src/"):
                continue
            if "/tests/" in rel or rel.startswith("tests/"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if any(tok in s for tok in FORBIDDEN):
                    violations.append(f"{rel}:{i}: use pipeline.file_utils.safe_write_text/bytes")
        except Exception:
            continue

    if violations:
        print("Direct Path.write_text/bytes found in src/:")
        for v in violations:
            print(" -", v)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
