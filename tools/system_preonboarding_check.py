# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path
import sys

from system.self_check import run_system_self_check


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    report = run_system_self_check(repo_root)
    for item in report.items:
        status = "[OK]" if item.ok else "[FAIL]"
        print(f"{status} {item.name} - {item.message}")
    if report.ok:
        print("Self-check completato: ambiente OK.")
        return 0
    print("Self-check fallito: correggere i problemi sopra prima di procedere.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
