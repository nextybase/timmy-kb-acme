# SPDX-License-Identifier: GPL-3.0-only
"""
DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[`*_~:.,'\"()\[\]{}]+", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def collect_files(root: Path) -> list[Path]:
    out: list[Path] = []
    if (root / "README.md").exists():
        out.append(root / "README.md")
    out.extend(sorted((root / "docs").glob("*.md")))
    return out


def check_file(root: Path, f: Path) -> list[tuple[str, str, str]]:
    text = f.read_text(encoding="utf-8", errors="ignore")
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    anchors = {slugify(m.group(1)) for m in re.finditer(r"^\s*#{1,6}\s+(.+)$", text, re.M)}
    bad: list[tuple[str, str, str]] = []
    for m in link_re.finditer(text):
        url = m.group(1).strip()
        if not url or url.startswith("http") or url.startswith("mailto:"):
            continue
        if url.startswith("#"):
            anchor = url[1:]
            if anchor and slugify(anchor) not in anchors:
                bad.append((str(f), f"missing anchor #{anchor}", url))
            continue
        path, _, anchor = url.partition("#")
        target = (f.parent / path).resolve()
        if not target.exists():
            bad.append((str(f), f"missing file {path}", url))
            continue
        if anchor:
            ttext = target.read_text(encoding="utf-8", errors="ignore")
            tans = {slugify(h) for h in re.findall(r"^\s*#{1,6}\s+(.+)$", ttext, re.M)}
            if slugify(anchor) not in tans:
                bad.append((str(f), f"missing anchor in target #{anchor}", url))
    return bad


def main() -> int:
    root = Path.cwd()
    files = collect_files(root)
    bad_all: list[tuple[str, str, str]] = []
    for f in files:
        bad_all.extend(check_file(root, f))
    if bad_all:
        print("Broken links/anchors:")
        for b in bad_all:
            print(" -", b[0], "::", b[1], "->", b[2])
        return 1
    print("All local links/anchors look good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
