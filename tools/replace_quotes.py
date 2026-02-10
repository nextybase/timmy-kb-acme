#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPLACEMENTS = {
    "\u201c": '"',   # left double quotation mark
    "\u201d": '"',   # right double quotation mark
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark
    "\u2013": "-",   # en dash
    "\u2014": "--",  # em dash
}

TEXT_EXTS = {
    ".md", ".txt",
    ".py",
    ".yml", ".yaml",
    ".toml", ".json",
    ".ini", ".cfg",
    ".rst",
}

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".pytest_cache",
}

def iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir() and p.name in SKIP_DIRS:
            # Skip whole subtree
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() in TEXT_EXTS:
            # Quick dir skip (cheap)
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            files.append(p)
    return files

def normalize_text(text: str) -> tuple[str, bool]:
    changed = False
    for old, new in REPLACEMENTS.items():
        if old in text:
            text = text.replace(old, new)
            changed = True
    return text, changed

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root (default: .)")
    ap.add_argument("--check", action="store_true", help="Fail if replacements would occur; do not modify files.")
    ap.add_argument("--files", nargs="*", help="Optional explicit file list (overrides scan).")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    paths = [Path(f) for f in (args.files or [])] if args.files else iter_text_files(root)

    touched: list[Path] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Ignore binaries / non-utf8
            continue

        new_text, changed = normalize_text(text)
        if not changed:
            continue

        touched.append(path)
        if args.check:
            continue
        path.write_text(new_text, encoding="utf-8")

    if args.check and touched:
        print("Smart quotes/dashes found in:", file=sys.stderr)
        for p in touched:
            print(f" - {p}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
