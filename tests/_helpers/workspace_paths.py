# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path


def local_workspace_name(slug: str) -> str:
    return f"timmy-kb-{slug}"


def local_workspace_dir(base: Path, slug: str) -> Path:
    return base / local_workspace_name(slug)
