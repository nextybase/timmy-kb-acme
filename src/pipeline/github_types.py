# SPDX-License-Identifier: GPL-3.0-or-later
"""Tipi condivisi per le utility GitHub."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["SupportsContext"]


@runtime_checkable
class SupportsContext(Protocol):
    """Protocol minimale per il contesto richiesto dalle utility GitHub."""

    slug: str
    md_dir: Path
    env: dict[str, Any]
    base_dir: Path
