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
    base_dir: Path
    raw_dir: Path
    md_dir: Path

    repo_root_dir: Optional[Path] = None
    semantic_dir: Optional[Path] = None
    config_dir: Optional[Path] = None

    redact_logs: bool = False
    run_id: Optional[str] = None
    skip_preview: bool = False
    no_interactive: bool = False

    @classmethod
    def from_dummy_workspace(cls, ws: dict[str, object]) -> "TestClientCtx":
        base = Path(ws["base"])
        raw = Path(ws.get("raw_dir", base / "raw"))
        md = Path(ws.get("book_dir", base / "book"))
        slug = str(ws.get("slug", "dummy"))
        semantic_root = Path(ws.get("semantic_dir", base / "semantic"))
        return cls(
            slug=slug,
            base_dir=base,
            raw_dir=raw,
            md_dir=md,
            repo_root_dir=base,
            semantic_dir=semantic_root,
            config_dir=base / "config",
        )


@dataclass
class TestSemanticCtx(TestClientCtx, SemanticContextProtocol):
    """Contesto per i test che richiedono SemanticContextProtocol."""

    skip_preview: bool = False
    no_interactive: bool = False
