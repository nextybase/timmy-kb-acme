from __future__ import annotations

import sys
from pathlib import Path

try:
    from ftfy import fix_text
except Exception as e:
    sys.stderr.write("ftfy non installato: pip install ftfy\n")
    sys.exit(2)


def main() -> int:
    root = Path("docs")
    changed = []
    for p in root.rglob("*.md"):
        txt = p.read_text(encoding="utf-8", errors="strict")
        fixed = fix_text(txt)
        if fixed != txt:
            p.write_text(fixed, encoding="utf-8", newline="\n")
            changed.append(p)
    for p in changed:
        print(f"FIXED: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
