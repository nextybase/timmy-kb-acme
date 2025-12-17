# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import List, Optional, TypedDict


class RelationContract(TypedDict):
    """Contratto minimo per ogni relazione tracciabile da Rosetta."""

    relation_id: str
    from_assertion: str
    to_assertion: str
    type: str
    provenance_ref: str


class AssertionContract(TypedDict, total=False):
    """Descrive un'assertion che alimenta la Knowledge Graph + Rosetta."""

    assertion_id: str
    source: str
    confidence: Optional[float]
    relations: List[str]


__all__ = [
    "AssertionContract",
    "RelationContract",
]
