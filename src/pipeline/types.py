# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Optional, TypedDict


class CapabilityAvailability(TypedDict):
    """Descrive lo stato di disponibilitÇÿ di una capability."""

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
    raw_dir: Path
    semantic_dir: Path
    source: str
    run_id: Optional[str]
    extra: dict[str, object] | None
