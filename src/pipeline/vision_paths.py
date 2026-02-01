# SPDX-License-Identifier: GPL-3.0-or-later
"""SSoT helpers for visionstatement.yaml paths (workspace only)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pipeline.path_utils import ensure_within_and_resolve

__all__ = ["vision_yaml_workspace_path"]


def vision_yaml_workspace_path(repo_root_dir: Path, *, pdf_path: Path | None = None) -> Path:
    """Return the workspace visionstatement.yaml path.

    Uses path-safety to keep the output within repo_root_dir.
    """
    base = Path(repo_root_dir)
    candidate = (
        (Path(pdf_path).parent / "visionstatement.yaml")
        if pdf_path is not None
        else (base / "config" / "visionstatement.yaml")
    )
    return cast(Path, ensure_within_and_resolve(base, candidate))
