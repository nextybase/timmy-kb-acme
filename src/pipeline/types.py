# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Optional, TypedDict


class CapabilityAvailability(TypedDict):
    """Descrive lo stato di disponibilità di una capability."""

    available: bool
    reason: Optional[str]


class WorkflowResult(TypedDict):
    """Contratto minimo per l'esito dei workflow CLI."""

    ok: bool
    message: str
    details: dict[str, object] | None


class TaggingPayload(TypedDict):
    """Descrive i dati principali del payload usato da Tag Onboarding."""

    workspace_slug: str
    normalized_dir: Path
    semantic_dir: Path
    run_id: Optional[str]
    extra: dict[str, object] | None


class ChunkRecord(TypedDict):
    """Contratto SSoT per descrivere un chunk di knowledge base."""

    id: str
    slug: str
    source_path: str
    text: str
    chunk_index: int
    created_at: str
    metadata: dict[str, object]
