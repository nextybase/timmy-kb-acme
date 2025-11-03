#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
fix_mojibake.py

Trova e corregge sequenze di mojibake comuni (UTF-8 mal decodificato come cp1252)
in file di testo del repository. Di default fa una dry-run e stampa un riepilogo;
con --apply scrive le modifiche.

Esempio:
  python scripts/fix_mojibake.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Sequenze note -> sostituzioni desiderate
REPLACEMENTS: Dict[str, str] = {
    # Dashes
    "—": "—",  # em dash
    "–": "–",  # en dash
    # Quotes/apostrophes
    "’": "’",
    "‘": "‘",
    "“": "“",
    "”": "”",
    # Ellipsis & bullets
    "…": "…",
    "•": "•",
    # Degree and middle dot
    "°": "°",
    "·": "·",
    # Non-breaking space turned to
    " ": " ",
    # Generic stray marker (use sparingly; keep after specific ones)
    "": "",
    # BOM rendered mojibake in content
    "Ã¯»¿": "",
    # Common Latin-1 vowels broken
    "à": "à",
    "á": "á",
    "è": "è",
    "é": "é",
    "ì": "ì",
    "ò": "ò",
    "ó": "ó",
    "ù": "ù",
    "ú": "ú",
    "ç": "ç",
    "ñ": "ñ",
    # Capital variants
    "À": "À",
    "É": "É",
}


DEFAULT_EXTS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".ps1",
    ".sh",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".csv",
    ".rst",
}

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "output",  # evitare di toccare artefatti/workspace
    "logs",
    "__pycache__",
}


def iter_files(root: Path, exts: Iterable[str]) -> Iterable[Path]:
    exts_l = {e.lower() for e in exts}
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if (d not in EXCLUDE_DIRS and not d.startswith(".")) or d == ".codex"]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts_l:
                yield p


def apply_replacements(text: str) -> Tuple[str, List[Tuple[str, int]]]:
    counts: List[Tuple[str, int]] = []
    out = text
    for k, v in REPLACEMENTS.items():
        if k in out:
            n = out.count(k)
            out = out.replace(k, v)
            counts.append((k, n))
    return out, counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Fix mojibake in repo files")
    ap.add_argument("--root", default=str(Path.cwd()), help="Root directory to scan")
    ap.add_argument("--apply", action="store_true", help="Write changes to disk")
    ap.add_argument(
        "--ext",
        action="append",
        help="File extension to include (repeat). Defaults to a safe set",
    )
    args = ap.parse_args()

    # Best-effort: forza stdout/stderr a UTF-8 o sostituisce caratteri non stampabili
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    root = Path(args.root).resolve()
    exts = set(args.ext) if args.ext else set(DEFAULT_EXTS)

    total_files = 0
    changed_files = 0
    total_changes = 0
    details: List[str] = []

    for fp in iter_files(root, exts):
        try:
            src = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # tenta cp1252 e poi converte a utf-8
            try:
                raw = fp.read_bytes()
                src = raw.decode("cp1252")
            except Exception:
                continue  # salta file binari o problematici
        total_files += 1
        fixed, counts = apply_replacements(src)
        if counts and fixed != src:
            changed_files += 1
            chg_sum = ", ".join([f"{k}x{n}" for k, n in counts])
            details.append(f"{fp}: {chg_sum}")
            total_changes += sum(n for _, n in counts)
            if args.apply:
                fp.write_text(fixed, encoding="utf-8", newline="\n")

    print(f"Scansionati: {total_files} file. Modificati: {changed_files}. Sostituzioni: {total_changes}.")
    if details:
        print("\nDettagli (prime 50):")
        for line in details[:50]:
            print(" - ", line)
    if not args.apply:
        print("\nDry-run: rieseguire con --apply per scrivere le modifiche.")


if __name__ == "__main__":
    main()
