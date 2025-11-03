#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable

SPDX_TOKEN = "SPDX-License-Identifier"
ENCODING_RE = re.compile(rb"^#.*coding[:=]\s*([-\w.]+)")

DEFAULT_INCLUDE_DIRS = ("src", "tests", "scripts")
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "node_modules",
}


def discover_python_files(
    roots: Iterable[Path], exclude_dirs: set[str]
) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            found.append(root.resolve())
            continue
        for p in root.rglob("*.py"):
            if any(part in exclude_dirs for part in p.parts):
                continue
            found.append(p.resolve())
    return sorted(set(found))


def has_spdx_header_bytes(head: list[bytes]) -> bool:
    return any(SPDX_TOKEN.encode("utf-8") in ln for ln in head)


def find_insert_index(lines: list[bytes]) -> int:
    i = 0
    if lines and lines[0].startswith(b"#!"):
        i = 1
    if i < len(lines) and ENCODING_RE.match(lines[i]):
        i += 1
    return i


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".spdx.tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def ensure_trailing_nl(b: bytes) -> bytes:
    return b if b.endswith(b"\n") else b + b"\n"


def process_file(
    path: Path, license_id: str, dry_run: bool = False
) -> tuple[bool, str]:
    try:
        with open(path, "rb") as fh:
            content = fh.read()
    except Exception as e:  # pragma: no cover - I/O failure path
        return False, f"SKIP (unreadable): {path} ({e})"

    if SPDX_TOKEN.encode("utf-8") in content:
        return False, f"OK (already has SPDX): {path}"

    lines = content.splitlines(keepends=True)
    head = lines[:8] if len(lines) >= 8 else lines
    if has_spdx_header_bytes(head):
        return False, f"OK (already has SPDX in head): {path}"

    insert_at = find_insert_index(lines)
    spdx_line = f"# {SPDX_TOKEN}: {license_id}\n".encode("utf-8")

    if insert_at > 0 and not lines[insert_at - 1].endswith(b"\n"):
        lines[insert_at - 1] = ensure_trailing_nl(lines[insert_at - 1])

    new_content = b"".join(
        lines[:insert_at] + [spdx_line] + lines[insert_at:]
    )
    if dry_run:
        return True, f"DRY-RUN would add SPDX to: {path}"
    try:
        atomic_write(path, new_content)
        return True, f"ADDED SPDX to: {path}"
    except Exception as e:  # pragma: no cover - should not happen
        return False, f"ERROR writing {path}: {e}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Insert SPDX headers into Python files that are missing them "
            "(safe & idempotent)."
        )
    )
    parser.add_argument(
        "--license-id",
        default="GPL-3.0-only",
        help="SPDX license identifier to insert (default: GPL-3.0-only)",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=list(DEFAULT_INCLUDE_DIRS),
        help="Directories or files to scan (default: src tests scripts)",
    )
    parser.add_argument(
        "--exclude-dirs",
        nargs="*",
        default=list(DEFAULT_EXCLUDE_DIRS),
        help="Directory names to exclude anywhere in the path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report files that would be changed, do not modify.",
    )
    args = parser.parse_args(argv)

    roots = [Path(p) for p in args.include]
    to_scan = discover_python_files(roots, set(args.exclude_dirs))

    changed = 0
    skipped = 0
    errors = 0
    for f in to_scan:
        chg, msg = process_file(f, args.license_id, dry_run=args.dry_run)
        print(msg)
        if chg and not args.dry_run:
            changed += 1
        elif msg.startswith("ERROR"):
            errors += 1
        else:
            skipped += 1

    print(
        f"\nSummary: changed={changed}, skipped={skipped}, "
        f"errors={errors}, scanned={len(to_scan)}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
