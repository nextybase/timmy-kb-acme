# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility condivise per risolvere i percorsi del contesto semantico."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

__all__ = ["ContextPaths", "resolve_context_paths"]


class ContextProtocol(Protocol):
    base_dir: Path | None
    raw_dir: Path | None
    md_dir: Path | None


@dataclass(frozen=True)
class ContextPaths:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def resolve_context_paths(context: Any, slug: str, *, paths_provider: Any) -> ContextPaths:
    """Risoluzione condivisa di base/raw/md a partire da un contesto."""
    paths = paths_provider(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or (base_dir / "raw"))
    md_dir = cast(Path, getattr(context, "md_dir", None) or (base_dir / "book"))
    return ContextPaths(base_dir=base_dir, raw_dir=raw_dir, md_dir=md_dir, slug=slug)
