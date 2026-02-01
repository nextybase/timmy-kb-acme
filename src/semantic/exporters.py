# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping, Sequence

from semantic.contracts import AssertionContract, RelationContract


def export_kg_json(
    *,
    assertions: Sequence[AssertionContract],
    relations: Sequence[RelationContract],
    explanations: Mapping[str, object],
    run_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    """Serializza una visione compatta del KG + explain output."""
    payload: dict[str, object] = {
        "assertions": list(assertions),
        "relations": list(relations),
        "explanations": dict(explanations),
        "metadata": {},
    }
    metadata: dict[str, object] = {}
    if run_id:
        metadata["run_id"] = run_id
    metadata["exported_at"] = timestamp or datetime.utcnow().isoformat()
    payload["metadata"] = metadata
    return payload


def export_kg_markdown(
    *,
    assertions: Iterable[AssertionContract],
    relations: Iterable[RelationContract],
    explanations: Mapping[str, object],
) -> str:
    """Genera un report Markdown minimale per audit."""
    sections: list[str] = []
    sections.append("## Assertions")
    for assertion in assertions:
        sections.append(f"- **{assertion.get('assertion_id', '<anon>')}** ({assertion.get('source', 'n/a')})")
        if confidence := assertion.get("confidence"):
            sections.append(f"  - confidence: {confidence}")
        if relations_list := assertion.get("relations"):
            sections.append(f"  - relations: {', '.join(relations_list)}")
    sections.append("\n## Relations")
    for relation in relations:
        sections.append(f"- **{relation['relation_id']}** {relation['type']}")
        sections.append(
            f"  - from: {relation['from_assertion']} "
            f"→ to: {relation['to_assertion']} "
            f"(prov: {relation['provenance_ref']})"
        )
    sections.append("\n## Explanations")
    for key, value in explanations.items():
        sections.append(f"- **{key}**: {value}")
    return "\n".join(sections)


__all__ = [
    "export_kg_json",
    "export_kg_markdown",
]
