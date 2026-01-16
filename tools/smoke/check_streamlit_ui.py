#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
Streamlit UI guard (cross-platform, Python)
- Evita dipendenza da bash/WSL; coerente con gli altri check in tools/dev/*.py
- Controlli:
  1) Router adoption: presenza di st.Page o st.navigation nel codice.
  2) Path-safety: vieta os.walk e Path.rglob.
  3) Preferenze UX: avvisa se st.page_link non è usato da nessuna parte.
  4) Logging UI: avvisa se ci sono logger senza prefisso 'ui.'

Uso:
    python tools/dev/check_streamlit_ui.py [--ci]
        --ci    tratta i warning come errori (exit 1)

Note: le deprecazioni Streamlit (experimental_ / cache / unsafe_allow_html / use_*_width)
      sono già coperte da check_streamlit_deprecations.py e check_ui_beta0_compliance.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
# Limitiamo il controllo alla UI per evitare falsi positivi sugli altri layer.
SRC = REPO_ROOT / "src" / "ui"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "tests",
    "scripts",  # evitiamo di auto-segnalarci
}

INCLUDE_EXT = {".py"}

FORBIDDEN_PATTERNS = {
    r"\bos\.walk\s*\(": "Use of os.walk detected. Usa iteratori sicuri (es. iter_safe_pdfs) e guardie path.",
    r"\brglob\s*\(": "Uso di Path.rglob rilevato. Preferisci util sicuri e bounded scan.",
}

REQUIRED_ROUTER_ANY = (
    r"\bst\.Page\s*\(",
    r"\bst\.navigation\s*\(",
)

PREFERRED_LINK = r"\bst\.page_link\s*\("

LOGGER_PATTERN = r"logging\.getLogger\s*\(\s*([\"'])(.*?)\1\s*\)"


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in INCLUDE_EXT:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def grep_count(root: Path, pattern: str) -> int:
    import re

    regex = re.compile(pattern)
    count = 0
    for file_path in iter_source_files(root):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if regex.search(text):
            count += 1
    return count


def grep_find(root: Path, pattern: str) -> list[tuple[Path, int, str]]:
    import re

    regex = re.compile(pattern)
    findings: list[tuple[Path, int, str]] = []
    for file_path in iter_source_files(root):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in regex.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append((file_path, line_no, m.group(0)))
    return findings


def check_router() -> list[str]:
    # Passa se trovi almeno uno fra st.Page e st.navigation nel codice UI.
    hits = sum(grep_count(SRC, p) for p in REQUIRED_ROUTER_ANY)
    if hits == 0:
        return ["Router APIs non rilevate (st.Page/st.navigation). Migrare al router nativo Streamlit (>=1.50)."]
    return []


def check_path_safety() -> list[str]:
    problems: list[str] = []
    for pattern, message in FORBIDDEN_PATTERNS.items():
        for file_path, line_no, match in grep_find(SRC, pattern):
            problems.append(f"{file_path}:{line_no}: {message} (trovato: '{match}')")
    return problems


def check_page_link() -> list[str]:
    warnings: list[str] = []
    if grep_count(SRC, PREFERRED_LINK) == 0:
        warnings.append(
            "st.page_link non rilevato: preferisci link dichiarativi alla navigazione manuale o anchor HTML."
        )
    return warnings


def check_logger_prefix() -> list[str]:
    import re

    warnings: list[str] = []
    regex = re.compile(LOGGER_PATTERN)
    for file_path in iter_source_files(SRC):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in regex.finditer(text):
            name = m.group(2) or ""
            if not name.startswith("ui."):
                line_no = text.count("\n", 0, m.start()) + 1
                warnings.append(f"{file_path}:{line_no}: logger senza prefisso 'ui.' -> getLogger('{name}')")
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true", help="tratta i warning come errori")
    args = parser.parse_args(argv)

    failures: list[str] = []
    warnings: list[str] = []

    failures += check_router()
    failures += check_path_safety()
    warnings += check_page_link()
    warnings += check_logger_prefix()

    if failures:
        print("[streamlit-ui-guard] Violazioni trovate:\n")
        for f in failures:
            print(" -", f)
    if warnings:
        print("\n[streamlit-ui-guard] Avvisi:\n")
        for w in warnings:
            print(" -", w)

    if failures:
        return 1
    if args.ci and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
