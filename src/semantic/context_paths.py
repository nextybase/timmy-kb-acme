# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility condivise per risolvere i percorsi del contesto semantico.

Contratto 1.0 Beta (layout-first):
- I path canonici (repo_root/raw/book) devono derivare esclusivamente da WorkspaceLayout.
- È vietato ricostruire i path con join manuali o leggere context.*_dir come override.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.exceptions import ConfigError
from pipeline.workspace_layout import WorkspaceLayout

__all__ = ["ContextPaths", "resolve_context_paths"]


@dataclass(frozen=True)
class ContextPaths:
    repo_root_dir: Path
    raw_dir: Path
    normalized_dir: Path
    book_dir: Path
    slug: str


def resolve_context_paths(layout: WorkspaceLayout) -> ContextPaths:
    """Risoluzione canonica (layout-first) di repo_root/raw/book."""
    return ContextPaths(
        repo_root_dir=layout.repo_root_dir,
        raw_dir=layout.raw_dir,
        normalized_dir=layout.normalized_dir,
        book_dir=layout.book_dir,
        slug=layout.slug,
    )


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name == "ContextProtocol":
        raise AttributeError("ContextProtocol rimosso (1.0 Beta): usa WorkspaceLayout e resolve_context_paths(layout).")
    raise AttributeError(name)


def _legacy_resolve_context_paths(*_a: Any, **_k: Any) -> None:  # pragma: no cover
    raise ConfigError("API legacy disabilitata (1.0 Beta): resolve_context_paths accetta solo WorkspaceLayout.")
