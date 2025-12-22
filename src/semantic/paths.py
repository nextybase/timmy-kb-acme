# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility neutra per risolvere i percorsi del workspace semantic."""

from __future__ import annotations

from pathlib import Path

from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.path_utils import validate_slug

__all__ = ["get_semantic_paths"]


def get_semantic_paths(slug: str) -> dict[str, Path]:
    """Restituisce i percorsi canonicali del workspace semantic per lo slug."""
    safe_slug = validate_slug(slug)
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{safe_slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }
