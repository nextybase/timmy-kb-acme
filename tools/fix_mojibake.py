#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
fix_mojibake.py

Trova e corregge sequenze di mojibake comuni (UTF-8 mal decodificato come cp1252)
in file di testo del repository. Di default fa una dry-run e stampa un riepilogo;
con --apply scrive le modifiche.

Esempio:
  python tools/fix_mojibake.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Sequenze note -> sostituzioni desiderate.
# Mappiamo i casi tipici di UTF-8 decodificato come cp1252/latin-1: niente no-op o placeholder.
REPLACEMENTS: Dict[str, str] = {
    # Punteggiatura smart
    "â€”": "—",
    "â€“": "–",
    "â€œ": "“",
    "â€�": "”",
    "â€": "”",
    "â€˜": "‘",
    "â€™": "’",
    "â€¦": "…",
    "â€¢": "•",
    "â†’": "→",
    # Simboli comuni
    "â‚¬": "€",
    "Â°": "°",
    "Â·": "·",
    "Â ": " ",
    "ï»¿": "",
    # Vocali/lettere accentate
    "Ã ": "à",
    "Ã¡": "á",
    "Ã¢": "â",
    "Ã¤": "ä",
    "Ã£": "ã",
    "Ã¨": "è",
    "Ã©": "é",
    "Ãª": "ê",
    "Ã«": "ë",
    "Ã¬": "ì",
    "Ã­": "í",
    "Ã®": "î",
    "Ã¯": "ï",
    "Ã²": "ò",
    "Ã³": "ó",
    "Ã´": "ô",
    "Ã¶": "ö",
    "Ãµ": "õ",
    "Ã¹": "ù",
    "Ãº": "ú",
    "Ã»": "û",
    "Ã¼": "ü",
    "Ã±": "ñ",
    "Ã§": "ç",
    "ÃŸ": "ß",
    # Maiuscole accentate frequenti
    "Ã€": "À",
    "Ã‰": "É",
    "Ãˆ": "È",
    "ÃŒ": "Ì",
    "Ã’": "Ò",
    "Ã™": "Ù",
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


def ensure_within(base: Path, target: Path) -> Path:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if os.name == "nt":
        base_resolved = Path(str(base_resolved).lower())
        target_resolved = Path(str(target_resolved).lower())
    if base_resolved not in target_resolved.parents and base_resolved != target_resolved:
        raise ValueError(f"{target} è fuori dal perimetro {base}")
    return target_resolved


def safe_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding=encoding, dir=path.parent) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


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
    if counts:
        out = unicodedata.normalize("NFC", out)
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
                resolved = ensure_within(root, fp)
                safe_write_text(resolved, fixed, encoding="utf-8")

    print(f"Scansionati: {total_files} file. Modificati: {changed_files}. Sostituzioni: {total_changes}.")
    if details:
        print("\nDettagli (prime 50):")
        for line in details[:50]:
            print(" - ", line)
    if not args.apply:
        print("\nDry-run: rieseguire con --apply per scrivere le modifiche.")


if __name__ == "__main__":
    main()
