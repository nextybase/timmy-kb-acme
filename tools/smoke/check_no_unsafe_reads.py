#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""DUMMY / SMOKE SUPER-TEST ONLY
FORBIDDEN IN RUNTIME-CORE (src/)
Fallback behavior is intentional and confined to this perimeter

Fail pre-commit if raw file reads are introduced outside safe helpers."""

from __future__ import annotations

import subprocess
import sys

RG_CMD = [
    "rg",
    "-n",
    "-P",
    r"(?<!\.)open\(|\.read_text\(|\.read_bytes\(",
    "src",
    "--glob",
    "!src/pipeline/path_utils.py",
    "--glob",
    "!src/pipeline/yaml_utils.py",
    "--glob",
    "!src/pipeline/file_utils.py",
    "--glob",
    "!src/**/__init__.py",
    "--glob",
    "!tests",
    "--glob",
    "!scripts",
]


def main() -> int:
    try:
        proc = subprocess.run(RG_CMD, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.stderr.write("ripgrep (rg) required by check_no_unsafe_reads.\n")
        return 1

    if proc.returncode == 0:
        # Matches found -> fail with guidance.
        sys.stdout.write(proc.stdout)
        sys.stdout.write(
            "\nFound potentially unsafe file reads. " "Use ensure_within_and_resolve()/open_for_read/read_text_safe.\n"
        )
        return 1
    if proc.returncode == 1 and not proc.stdout and not proc.stderr:
        # No matches; success.
        return 0
    # Propagate unexpected error output.
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
