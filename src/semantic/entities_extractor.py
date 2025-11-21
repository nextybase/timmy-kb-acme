# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/entities_extractor.py
"""Estrazione di entità area-aware tramite SpaCy + lexicon.

Questo modulo è puro: nessun I/O, nessun import time costoso (SpaCy viene
passato già caricato). Serve come step intermedio prima di salvare nel DB
`doc_entities`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from spacy.language import Language
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span

from semantic.lexicon import LexiconEntry

# Tipi di supporto
Lexicon = Dict[str, Dict[str, LexiconEntry]]


@dataclass(frozen=True)
class DocEntityHit:
    """Singola occorrenza di un'entità in un doc SpaCy."""

    doc_uid: str
    area_key: str
    entity_id: str
    span: Span | None
    confidence: float


def build_lexicon_map(entries: Iterable[LexiconEntry]) -> Lexicon:
    """Converte la lista di LexiconEntry in una mappa area->entity."""
    lexicon: Lexicon = {}
    for entry in entries:
        area_bucket = lexicon.setdefault(entry.area_key, {})
        area_bucket[entry.entity_id] = entry
    return lexicon


def make_phrase_matcher(
    nlp: Language,
    lexicon: Lexicon,
    attr: str = "LOWER",
) -> PhraseMatcher:
    """Crea un PhraseMatcher popolato con tutti i termini del lexicon."""
    matcher = PhraseMatcher(nlp.vocab, attr=attr)
    for area_key, entities in lexicon.items():
        for entity_id, entity in entities.items():
            patterns = []
            for term in entity.terms:
                text = term.strip()
                if not text:
                    continue
                patterns.append(nlp.make_doc(text))
            if patterns:
                matcher.add(f"{area_key}::{entity_id}", patterns)
    return matcher


def _decode_pattern_id(vocab_strings, pattern_id: int) -> Tuple[str, str]:
    """Decodifica l'ID del pattern "area_key::entity_id"."""
    text = str(vocab_strings[pattern_id])
    if "::" not in text:
        return "unknown", text
    return text.split("::", 1)


def extract_doc_entities(
    doc_uid: str,
    doc: Doc,
    matcher: PhraseMatcher,
) -> List[DocEntityHit]:
    """Usa PhraseMatcher per estrarre menzioni di entità dal doc (grezze)."""
    matches = matcher(doc)
    if not matches:
        return []

    doc_len = max(1, len(doc))
    hits: List[DocEntityHit] = []
    for match_id, start, end in matches:
        span = doc[start:end]
        area_key, entity_id = _decode_pattern_id(doc.vocab.strings, match_id)

        # Confidence euristica: mix posizione e lunghezza tokenizzata
        position_score = 1.0 - (start / doc_len)
        length_score = min(1.0, len(span.text) / 10.0)
        confidence = max(0.0, min(1.0, 0.5 * position_score + 0.5 * length_score))

        hits.append(
            DocEntityHit(
                doc_uid=doc_uid,
                area_key=area_key,
                entity_id=entity_id,
                span=span,
                confidence=confidence,
            )
        )
    return hits


def reduce_doc_entities(
    hits: Iterable[DocEntityHit],
    max_per_area: int = 5,
    min_confidence: float = 0.4,
) -> List[DocEntityHit]:
    """Aggrega per (doc, area, entity), applica soglia e limita per area."""
    aggregated: Dict[Tuple[str, str, str], List[float]] = {}
    for hit in hits:
        key = (hit.doc_uid, hit.area_key, hit.entity_id)
        aggregated.setdefault(key, []).append(hit.confidence)

    by_area: Dict[str, List[DocEntityHit]] = {}
    for (doc_uid, area_key, entity_id), values in aggregated.items():
        avg_conf = sum(values) / len(values)
        if avg_conf < min_confidence:
            continue
        reduced = DocEntityHit(
            doc_uid=doc_uid,
            area_key=area_key,
            entity_id=entity_id,
            span=None,
            confidence=avg_conf,
        )
        by_area.setdefault(area_key, []).append(reduced)

    reduced_hits: List[DocEntityHit] = []
    for _area_key, area_hits in by_area.items():
        area_hits.sort(key=lambda h: h.confidence, reverse=True)
        reduced_hits.extend(area_hits[: max(1, int(max_per_area))])

    return reduced_hits
