# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/entities_review.py
"""Backend di revisione per doc_entities (SpaCy/HiTL).

Funzioni pure riusabili da CLI e UI, nessun side-effect a import-time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pipeline.exceptions import ConfigError

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=None).strftime(ISO_FORMAT)


@dataclass(frozen=True)
class TagReviewItem:
    doc_uid: str
    area_key: str
    entity_id: str
    label: str
    confidence: float
    origin: str
    status: str


def build_entity_label_index(mapping: Mapping[str, Any]) -> Dict[Tuple[str, str], str]:
    """Indice (area_key, entity_id) -> label canonica dal semantic_mapping."""
    index: Dict[Tuple[str, str], str] = {}
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
            index[(area_key, ent_id)] = label or ent_id
    return index


def fetch_tags_for_doc(
    conn: sqlite3.Connection,
    doc_uid: str,
    mapping: Mapping[str, Any],
    status_filter: Optional[Sequence[str]] = None,
) -> List[TagReviewItem]:
    """Ritorna i tag di doc_entities per un doc (filtrabili per status)."""
    if status_filter is None:
        status_filter = ("suggested", "approved", "rejected")
    placeholders = ",".join("?" for _ in status_filter)
    params: List[Any] = [doc_uid, *status_filter]

    query = (
        "SELECT doc_uid, area_key, entity_id, confidence, origin, status "
        "FROM doc_entities WHERE doc_uid = ? AND status IN (" + placeholders + ") "
        "ORDER BY area_key, confidence DESC, entity_id"
    )
    rows = conn.execute(query, params).fetchall()
    if not rows:
        return []

    label_index = build_entity_label_index(mapping)
    items: List[TagReviewItem] = []
    for row in rows:
        _doc_uid, area_key, entity_id, confidence, origin, status = row
        label = label_index.get((area_key, entity_id), entity_id)
        items.append(
            TagReviewItem(
                doc_uid=str(_doc_uid),
                area_key=str(area_key),
                entity_id=str(entity_id),
                label=label,
                confidence=float(confidence),
                origin=str(origin),
                status=str(status),
            )
        )
    return items


def fetch_docs_with_suggested_tags(conn: sqlite3.Connection, limit: int = 50) -> List[Tuple[str, int]]:
    """Lista doc_uid con tag 'suggested' e relativo conteggio, ordinati per conteggio."""
    rows = conn.execute(
        """
        SELECT doc_uid, COUNT(*) AS cnt
        FROM doc_entities
        WHERE status = 'suggested'
        GROUP BY doc_uid
        ORDER BY cnt DESC, doc_uid
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(str(r[0]), int(r[1])) for r in rows]


def update_tag_status(
    conn: sqlite3.Connection,
    doc_uid: str,
    area_key: str,
    entity_id: str,
    new_status: str,
    origin: Optional[str] = None,
) -> None:
    """Aggiorna lo status di un tag (opzionalmente filtrando per origin)."""
    if new_status not in {"suggested", "approved", "rejected"}:
        raise ConfigError(f"Invalid new_status: {new_status}")

    params: List[Any] = [new_status, _now_iso(), doc_uid, area_key, entity_id]
    query = "UPDATE doc_entities SET status = ?, updated_at = ? " "WHERE doc_uid = ? AND area_key = ? AND entity_id = ?"
    if origin is not None:
        query += " AND origin = ?"
        params.append(origin)
    conn.execute(query, params)


def bulk_update_tag_status(
    conn: sqlite3.Connection,
    items: Iterable[TagReviewItem],
    new_status: str,
) -> None:
    """Aggiorna in bulk lo status per una lista di TagReviewItem."""
    if new_status not in {"suggested", "approved", "rejected"}:
        raise ConfigError(f"Invalid new_status: {new_status}")
    now = _now_iso()
    rows = [(new_status, now, it.doc_uid, it.area_key, it.entity_id, it.origin) for it in items]
    conn.executemany(
        """
        UPDATE doc_entities
        SET status = ?, updated_at = ?
        WHERE doc_uid   = ?
          AND area_key  = ?
          AND entity_id = ?
          AND origin    = ?
        """,
        rows,
    )
