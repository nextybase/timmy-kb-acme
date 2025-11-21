# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/lexicon.py
"""Costruzione di un lessico SpaCy a partire da semantic_mapping.yaml.

Il mapping resta SSoT (Vision): questo modulo legge e normalizza in una forma
utilizzabile dal matcher (termine -> (area_key, entity_id)).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class LexiconEntry:
    area_key: str
    entity_id: str
    label: str
    terms: Tuple[str, ...]


def _iter_entities(mapping: Dict[str, Any]) -> Iterable[LexiconEntry]:
    """Esporta le entità definite nel mapping, con sinonimi/label come termini."""
    areas = mapping.get("areas") or []
    for area in areas:
        area_key = str(area.get("key", "")).strip().lower()
        if not area_key:
            continue
        correlazioni = area.get("correlazioni") or {}
        entities = correlazioni.get("entities") or []
        for ent in entities:
            ent_id = str(ent.get("id", "")).strip().lower()
            if not ent_id:
                continue
            label = str(ent.get("label", "")).strip()
            raw_terms: List[str] = []
            if label:
                raw_terms.append(label)
            raw_terms.append(ent_id)
            syns = ent.get("syn") or []
            if isinstance(syns, (list, tuple, set)):
                raw_terms.extend(str(s).strip() for s in syns if str(s).strip())
            terms_norm = tuple({t.lower() for t in raw_terms if t})
            if not terms_norm:
                continue
            yield LexiconEntry(area_key=area_key, entity_id=ent_id, label=label or ent_id, terms=terms_norm)


def _glossary_terms(mapping: Dict[str, Any]) -> Iterable[str]:
    """Restituisce eventuali hint dal glossario per arricchire termini esistenti."""
    glossario = (mapping.get("system_folders") or {}).get("glossario") or {}
    for term in glossario.get("terms_hint") or []:
        candidate = str(term).strip().lower()
        if candidate:
            yield candidate


def build_lexicon(mapping: Dict[str, Any]) -> List[LexiconEntry]:
    """Crea un elenco di LexiconEntry (area, entity_id, termini) dal mapping."""
    entries: List[LexiconEntry] = list(_iter_entities(mapping or {}))
    if not entries:
        return []

    glossary = set(_glossary_terms(mapping))
    if glossary:
        enriched: List[LexiconEntry] = []
        for entry in entries:
            # aggiungi termini del glossario che coincidono con l'id o label
            extra_terms = [t for t in glossary if t == entry.entity_id or t == entry.label.lower()]
            if extra_terms:
                merged_terms = tuple({*entry.terms, *extra_terms})
                enriched.append(
                    LexiconEntry(
                        area_key=entry.area_key,
                        entity_id=entry.entity_id,
                        label=entry.label,
                        terms=merged_terms,
                    )
                )
            else:
                enriched.append(entry)
        entries = enriched
    return entries
