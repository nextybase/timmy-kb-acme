# SPDX-License-Identifier: GPL-3.0-only
# tests/support/contexts.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from semantic.types import ClientContextProtocol, SemanticContextProtocol


@dataclass
class TestClientCtx(ClientContextProtocol):
    """Contesto minimale per i test, compatibile con ClientContextProtocol.

    Non carica config/env: è solo un contenitore di path usato nei test.
    """

    slug: str
    repo_root_dir: Path
    semantic_dir: Path
    config_dir: Path

    redact_logs: bool = False
    run_id: Optional[str] = None
    skip_preview: bool = False
    no_interactive: bool = False

    @classmethod
    def from_dummy_workspace(cls, ws: dict[str, object]) -> "TestClientCtx":
        slug = str(ws["slug"])
        repo_root_dir = Path(ws["repo_root_dir"])
        semantic_dir = Path(ws["semantic_dir"])
        config_dir = Path(ws["config_dir"])
        return cls(
            slug=slug,
            repo_root_dir=repo_root_dir,
            semantic_dir=semantic_dir,
            config_dir=config_dir,
        )


@dataclass
class TestSemanticCtx(TestClientCtx, SemanticContextProtocol):
    """Contesto per i test che richiedono SemanticContextProtocol."""

    skip_preview: bool = False
    no_interactive: bool = False
