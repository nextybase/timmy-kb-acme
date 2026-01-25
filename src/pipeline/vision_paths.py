# SPDX-License-Identifier: GPL-3.0-only
"""SSoT helpers for Vision YAML paths (workspace vs repo root)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pipeline.path_utils import ensure_within_and_resolve

__all__ = ["vision_yaml_workspace_path", "vision_yaml_repo_path"]


def vision_yaml_workspace_path(repo_root_dir: Path, *, pdf_path: Path | None = None) -> Path:
    """Return the workspace Vision YAML path (visionstatement.yaml).

    Uses path-safety to keep the output within repo_root_dir.
    """
    base = Path(repo_root_dir)
    candidate = (
        (Path(pdf_path).parent / "visionstatement.yaml")
        if pdf_path is not None
        else (base / "config" / "visionstatement.yaml")
    )
    return cast(Path, ensure_within_and_resolve(base, candidate))


def vision_yaml_repo_path(repo_root_dir: Path) -> Path:
    """Return the repo Vision YAML path (vision_statement.yaml)."""
    base = Path(repo_root_dir)
    candidate = base / "config" / "vision_statement.yaml"
    return cast(Path, ensure_within_and_resolve(base, candidate))
