# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI_ROOT = ROOT / "src" / "ui"

PATTERNS = [
    ("TIMMY_VISION_SKIP_SCHEMA_CHECK", re.compile(r"TIMMY_VISION_SKIP_SCHEMA_CHECK")),
    ("allow_fallback=True", re.compile(r"\ballow_fallback\s*=\s*True\b")),
    ("strict=False", re.compile(r"\bensure_dotenv_loaded\s*\([^)]*strict\s*=\s*False\b")),
    ("strict=False", re.compile(r"\bget_env_var\s*\([^)]*strict\s*=\s*False\b")),
    ("strict=False", re.compile(r"\bget_bool\s*\([^)]*strict\s*=\s*False\b")),
    ("strict=False", re.compile(r"\bget_int\s*\([^)]*strict\s*=\s*False\b")),
]


def _scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        exc_name = type(exc).__name__
        violations.append(f"{path}:{exc_name}: failed to read utf-8")
        return violations
    for idx, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            if pattern.search(line):
                violations.append(f"{path}:{idx}: {label}")
    return violations


def main() -> int:
    if not UI_ROOT.exists():
        print("ui strict guard: src/ui missing")
        return 1
    violations: list[str] = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        violations.extend(_scan_file(path))
    if violations:
        print("ui strict guard: violations found")
        for item in violations:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
