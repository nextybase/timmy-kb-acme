# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/entities_frontmatter.py
"""Arricchisce il frontmatter con entità e relazioni suggerite (doc_entities).

Principi:
- Nessun side-effect: richiede conn già aperta e mapping già caricato.
- Fail-soft: se doc_uid manca o non ci sono entità approvate, restituisce intatto.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Set


@dataclass(frozen=True)
class EntityRecord:
    area_key: str
    entity_id: str
    label: str


@dataclass(frozen=True)
class RelationRecord:
    area_key: str
    subj: str
    pred: str
    obj: str


def load_entities_for_doc(conn: sqlite3.Connection, doc_uid: str) -> List[EntityRecord]:
    """Legge le entità approvate per doc_uid dalla tabella doc_entities."""
    rows = conn.execute(
        """
        SELECT area_key, entity_id
        FROM doc_entities
        WHERE doc_uid = ?
          AND status = 'approved'
        """,
        (doc_uid,),
    ).fetchall()
    return [EntityRecord(area_key=str(r[0]), entity_id=str(r[1]), label="") for r in rows]


def build_entity_label_index(mapping: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    """Indice area_key -> entity_id -> label canonica dal semantic_mapping."""
    index: Dict[str, Dict[str, str]] = {}
    for area in mapping.get("areas", []) or []:
        area_key = str(area.get("key", "")).strip()
        if not area_key:
            continue
        correlazioni = area.get("correlazioni") or {}
        entities = correlazioni.get("entities") or []
        for ent in entities:
            ent_id = str(ent.get("id", "")).strip()
            if not ent_id:
                continue
            label = str(ent.get("label", "") or ent_id).strip()
            index.setdefault(area_key, {})[ent_id] = label or ent_id
    return index


def enrich_entity_labels(entities: List[EntityRecord], label_index: Dict[str, Dict[str, str]]) -> List[EntityRecord]:
    """Applica le label canoniche dal mapping alle entità lette dal DB."""
    enriched: List[EntityRecord] = []
    for ent in entities:
        label = label_index.get(ent.area_key, {}).get(ent.entity_id, ent.entity_id)
        enriched.append(EntityRecord(area_key=ent.area_key, entity_id=ent.entity_id, label=label))
    return enriched


def build_relations_for_doc(mapping: Mapping[str, Any], entities: List[EntityRecord]) -> List[RelationRecord]:
    """Restituisce relazioni whose subj/obj sono presenti nello stesso doc."""
    if not entities:
        return []

    present_by_area: Dict[str, Set[str]] = {}
    for ent in entities:
        present_by_area.setdefault(ent.area_key, set()).add(ent.entity_id)

    relations: List[RelationRecord] = []
    for area in mapping.get("areas", []) or []:
        area_key = str(area.get("key", "")).strip()
        if not area_key:
            continue
        present_ids = present_by_area.get(area_key)
        if not present_ids:
            continue
        correlazioni = area.get("correlazioni") or {}
        rels = correlazioni.get("relations") or []
        for rel in rels:
            subj = str(rel.get("subj", "")).strip()
            obj = str(rel.get("obj", "")).strip()
            pred = str(rel.get("pred", "")).strip()
            if not subj or not obj or not pred:
                continue
            if subj in present_ids and obj in present_ids:
                relations.append(RelationRecord(area_key=area_key, subj=subj, pred=pred, obj=obj))
    return relations


def enrich_frontmatter_with_entities(
    frontmatter: Dict[str, Any],
    conn: sqlite3.Connection,
    mapping: Mapping[str, Any],
) -> Dict[str, Any]:
    """Arricchisce frontmatter con entities/relations_hint se presenti in doc_entities."""
    doc_uid = str(frontmatter.get("doc_uid", "")).strip()
    if not doc_uid:
        return frontmatter

    raw_entities = load_entities_for_doc(conn, doc_uid)
    if not raw_entities:
        return frontmatter

    label_index = build_entity_label_index(mapping)
    entities = enrich_entity_labels(raw_entities, label_index)
    relations = build_relations_for_doc(mapping, entities)

    if not entities and not relations:
        return frontmatter

    fm = dict(frontmatter)
    if entities:
        fm["entities"] = [{"id": ent.entity_id, "label": ent.label, "area_key": ent.area_key} for ent in entities]
    if relations:
        fm["relations_hint"] = [
            {"subj": rel.subj, "pred": rel.pred, "obj": rel.obj, "area_key": rel.area_key} for rel in relations
        ]
    return fm
