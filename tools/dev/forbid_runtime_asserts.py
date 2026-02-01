# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    # Controlla solo file Python sotto src/ (non tests/)
    violated: list[str] = []
    for arg in argv:
        p = Path(arg)
        try:
            if not p.suffix == ".py":
                continue
            # Permetti assert nei test, vieta in src/
            rel = p.as_posix()
            if not rel.startswith("src/"):
                continue
            if "/tests/" in rel or rel.startswith("tests/"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            # un semplice check: 'assert ' non nei commenti (best-effort)
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if "assert " in s:
                    violated.append(f"{rel}:{i}")
        except Exception:
            # Non bloccare i commit per errori di lettura non critici
            continue

    if violated:
        print("Found runtime asserts in src/ (use explicit exceptions instead):")
        for v in violated:
            print(" -", v)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
