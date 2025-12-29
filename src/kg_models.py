# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TagNode:
    """Nodo di tag nel Knowledge Graph."""

    id: str
    label: str
    description: str
    category: str
    status: str
    language: str
    aliases: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TagRelation:
    """Relazione semantica tra due tag nel Knowledge Graph."""

    source: str
    target: str
    type: str
    confidence: float
    review_status: str
    id: Optional[str] = None
    provenance: Optional[str] = None
    notes: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TagKnowledgeGraph:
    """Rappresentazione in memoria del Knowledge Graph dei tag."""

    schema_version: str
    namespace: str
    generated_by: Optional[str] = None
    generated_at: Optional[str] = None
    source: Dict[str, Any] = field(default_factory=dict)
    tags: List[TagNode] = field(default_factory=list)
    relations: List[TagRelation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TagKnowledgeGraph":
        """Costruisce un TagKnowledgeGraph a partire dal JSON prodotto da l'assistant."""
        tags_data = data.get("tags", [])
        relations_data = data.get("relations", [])

        tags = [
            TagNode(
                id=t["id"],
                label=t["label"],
                description=t["description"],
                category=t.get("category", ""),
                status=t.get("status", "active"),
                language=t.get("language", "it"),
                aliases=t.get("aliases", []) or [],
                examples=t.get("examples", []) or [],
                extra={
                    k: v
                    for k, v in t.items()
                    if k
                    not in {
                        "id",
                        "label",
                        "description",
                        "category",
                        "status",
                        "language",
                        "aliases",
                        "examples",
                    }
                },
            )
            for t in tags_data
        ]

        relations = [
            TagRelation(
                id=r.get("id"),
                source=r["source"],
                target=r["target"],
                type=r["type"],
                confidence=float(r.get("confidence", 0.0)),
                provenance=r.get("provenance"),
                review_status=r.get("review_status", "pending"),
                notes=r.get("notes"),
                extra={
                    k: v
                    for k, v in r.items()
                    if k
                    not in {
                        "id",
                        "source",
                        "target",
                        "type",
                        "confidence",
                        "provenance",
                        "review_status",
                        "notes",
                    }
                },
            )
            for r in relations_data
        ]

        return cls(
            schema_version=data.get("schema_version", "kg-tags-0.1"),
            namespace=data.get("namespace", ""),
            generated_by=data.get("generated_by"),
            generated_at=data.get("generated_at"),
            source=data.get("source", {}) or {},
            tags=tags,
            relations=relations,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializza il Knowledge Graph in un dict JSON-compatibile."""
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at,
            "source": self.source,
            "tags": [
                {
                    "id": t.id,
                    "label": t.label,
                    "description": t.description,
                    "category": t.category,
                    "status": t.status,
                    "language": t.language,
                    "aliases": t.aliases,
                    "examples": t.examples,
                    **(t.extra or {}),
                }
                for t in self.tags
            ],
            "relations": [
                {
                    "id": r.id,
                    "source": r.source,
                    "target": r.target,
                    "type": r.type,
                    "confidence": r.confidence,
                    "provenance": r.provenance,
                    "review_status": r.review_status,
                    "notes": r.notes,
                    **(r.extra or {}),
                }
                for r in self.relations
            ],
        }
