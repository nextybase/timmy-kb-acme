# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper per determinare la root del repository (SSoT pipeline.paths)."""
from __future__ import annotations

from pathlib import Path

from pipeline.paths import get_repo_root as _get_repo_root


def get_repo_root(*, allow_env: bool = True) -> Path:
    """Wrapper SSoT: delega a pipeline.paths.get_repo_root (env-first, no fallback UI-specific)."""
    return _get_repo_root(allow_env=allow_env)


__all__ = ["get_repo_root"]
