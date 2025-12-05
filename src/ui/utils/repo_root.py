# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper per determinare la root del repository."""
from __future__ import annotations

from pathlib import Path

MARKER_FILES = {".git", "pyproject.toml"}


def _find_repo_root(start_dir: Path) -> Path:
    """
    Risale le directory partendo da `start_dir` finche non trova un marker di repo.
    Marker supportati: `.git` o `pyproject.toml`. Fallback: `Path.cwd()`.
    """
    for candidate in (start_dir, *start_dir.parents):
        if any((candidate / marker).exists() for marker in MARKER_FILES):
            return candidate
    return Path.cwd().resolve()


def get_repo_root() -> Path:
    """Restituisce la root del repository o `Path.cwd()` come fallback sicuro."""
    return _find_repo_root(Path(__file__).resolve().parent)
