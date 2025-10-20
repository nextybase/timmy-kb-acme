#!/usr/bin/env python3
"""Fail if deprecated Streamlit API patterns are present."""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional, Tuple


CommandResult = Tuple[str, str]


def run_rg(pattern: str, description: str) -> Optional[CommandResult]:
    """Run ripgrep for the given pattern and return matches."""
    cmd: List[str] = [
        "rg",
        "--color=never",
        "-n",
        "--glob",
        "!docs/**",
        "--glob",
        "!scripts/dev/check_streamlit_deprecations.py",
        "--glob",
        "!apply_changes.py",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return description, result.stdout.strip()

    if result.returncode == 1:
        return None

    sys.stderr.write(f"[streamlit-guard] errore eseguendo {' '.join(cmd)}\n")
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


def main() -> int:
    checks = [
        (r"use_(container|column)_width\s*=", "use_(container|column)_width"),
        (r"unsafe_allow_html\s*=", "unsafe_allow_html="),
        (r"st\.experimental_", "st.experimental_*"),
        (r"st\.cache\(", "st.cache("),
    ]

    findings: List[CommandResult] = []
    for pattern, description in checks:
        match = run_rg(pattern, description)
        if match is not None:
            findings.append(match)

    if not findings:
        return 0

    sys.stderr.write("[streamlit-guard] pattern Streamlit deprecati trovati:\n")
    for description, output in findings:
        sys.stderr.write(f"\n=== {description} ===\n{output}\n")
    sys.stderr.write("\nRimuovi le occorrenze sopra per rispettare le linee guida Streamlit 1.50.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
