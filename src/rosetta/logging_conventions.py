# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Any, Optional

EVENT_PREFIX = "rosetta"


def event_name(action: str) -> str:
    """Genera il nome dell’evento (es. `rosetta.check_coherence`)."""
    action_clean = action.strip().lower()
    if not action_clean.startswith(f"{EVENT_PREFIX}."):
        return f"{EVENT_PREFIX}.{action_clean}"
    return action_clean


def build_rosetta_event_extra(
    *,
    event: str,
    slug: Optional[str] = None,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    assertion_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    assertions_count: Optional[int] = None,
    metadata_fields_count: Optional[int] = None,
    candidate_fields_count: Optional[int] = None,
    provenance_fields_count: Optional[int] = None,
) -> dict[str, Any]:
    """Costruisce un extra dict coerente con le convenzioni per Rosetta."""
    extra: dict[str, Any] = {"event": event}
    field_map = {
        "slug": slug,
        "client_slug": slug,
        "run_id": run_id,
        "step_id": step_id,
        "artifact_id": artifact_id,
        "assertion_id": assertion_id,
        "trace_id": trace_id,
        "assertions_count": assertions_count,
        "metadata_fields_count": metadata_fields_count,
        "candidate_fields_count": candidate_fields_count,
        "provenance_fields_count": provenance_fields_count,
    }
    for key, value in field_map.items():
        if value is None:
            continue
        extra[key] = value
    return extra


__all__ = [
    "EVENT_PREFIX",
    "event_name",
    "build_rosetta_event_extra",
]
