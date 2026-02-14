# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/entities_runner.py
"""Runner per scrivere entita area-aware in doc_entities (strict/fail-fast)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, cast

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, iter_safe_pdfs
from semantic.config import load_semantic_config
from semantic.document_ingest import read_document
from semantic.entities_extractor import (
    DocEntityHit,
    build_lexicon_map,
    extract_doc_entities,
    make_phrase_matcher,
    reduce_doc_entities,
)
from semantic.lexicon import build_lexicon
from storage.tags_store import DocEntityRecord, save_doc_entities

LOG = get_structured_logger("semantic.entities_runner")


def _read_document_text(pdf_path: Path) -> str:
    doc = read_document(pdf_path)
    return cast(str, doc.full_text)


def _load_spacy(model_name: str) -> Any:
    import spacy

    return spacy.load(model_name)


def run_doc_entities_pipeline(
    *,
    repo_root_dir: Path,
    raw_dir: Path,
    semantic_dir: Path,
    db_path: Path,
    slug: str,
    logger: logging.Logger | None = None,
    max_per_area: int = 5,
    min_confidence: float = 0.4,
) -> dict[str, Any]:
    """
    Estrae entita' dai PDF e le salva nel DB (tabella doc_entities).

    Guardrail (CORE, low-entropy):
    - no fallback/non-strict;
    - ogni errore runtime alza eccezione typed.
    """
    log = logger or LOG
    backend = os.environ.get("TAGS_NLP_BACKEND", "spacy").strip().lower()
    if backend not in ("spacy",):
        raise ConfigError(
            f"entities.backend.invalid for slug={slug}: backend={backend}",
            slug=slug,
            file_path=semantic_dir,
        )

    workspace_root = repo_root_dir
    perimeter_root = repo_root_dir
    raw_dir = ensure_within_and_resolve(perimeter_root, raw_dir)
    db_path = ensure_within_and_resolve(perimeter_root, db_path)
    semantic_dir = ensure_within_and_resolve(perimeter_root, semantic_dir)
    ensure_within(perimeter_root, raw_dir)
    ensure_within(perimeter_root, semantic_dir)
    ensure_within(perimeter_root, db_path)

    pdf_paths = list(iter_safe_pdfs(raw_dir))
    if len(pdf_paths) == 0:
        raise ConfigError(
            f"entities.input.no_pdfs for slug={slug}",
            slug=slug,
            file_path=raw_dir,
        )

    try:
        cfg = load_semantic_config(workspace_root, slug=slug)
    except Exception as exc:  # pragma: no cover
        raise ConfigError(
            f"entities.config.load failed for slug={slug}",
            slug=slug,
            file_path=(workspace_root / "config" / "config.yaml"),
        ) from exc

    try:
        mapping = cfg.mapping or {}
        lexicon_entries = build_lexicon(mapping)
        lexicon = build_lexicon_map(lexicon_entries)
        if not lexicon:
            raise ConfigError(
                f"entities.lexicon.empty for slug={slug}",
                slug=slug,
                file_path=(semantic_dir / "semantic_mapping.yaml"),
            )

        nlp = _load_spacy(cfg.spacy_model)
        matcher = make_phrase_matcher(nlp, lexicon)
    except Exception as exc:
        raise PipelineError(
            f"entities.spacy.load failed for slug={slug}",
            slug=slug,
            file_path=semantic_dir,
        ) from exc

    hits_to_save: list[DocEntityHit] = []
    processed_pdfs = 0
    for pdf_path in pdf_paths:
        processed_pdfs += 1
        rel_uid = pdf_path.relative_to(repo_root_dir).as_posix()
        try:
            text = _read_document_text(pdf_path)
        except Exception as exc:
            raise PipelineError(
                f"entities.pdf.read failed for slug={slug}",
                slug=slug,
                file_path=pdf_path,
            ) from exc
        if not text:
            continue
        doc = nlp(text)
        doc_hits: Iterable[DocEntityHit] = extract_doc_entities(rel_uid, doc, matcher)
        reduced = reduce_doc_entities(
            doc_hits,
            max_per_area=max_per_area,
            min_confidence=min_confidence,
        )
        hits_to_save.extend(reduced)

    if not hits_to_save:
        return {
            "entities_written": 0,
            "processed_pdfs": int(processed_pdfs),
            "reason": "processed",
            "backend": backend,
        }

    try:
        records = [
            DocEntityRecord(
                doc_uid=hit.doc_uid,
                area_key=hit.area_key,
                entity_id=hit.entity_id,
                confidence=hit.confidence,
                origin="spacy",
            )
            for hit in hits_to_save
        ]
        save_doc_entities(db_path, records)
        hits_count = len(records)
    except Exception as exc:
        raise PipelineError(
            f"entities.persist failed for slug={slug}",
            slug=slug,
            file_path=db_path,
        ) from exc
    log.info(
        "semantic.entities.saved",
        extra={
            "count": hits_count,
            "spacy_model": cfg.spacy_model,
            "slug": cfg.slug,
        },
    )
    return {
        "entities_written": int(hits_count),
        "processed_pdfs": int(processed_pdfs),
        "reason": "processed",
        "backend": backend,
    }
