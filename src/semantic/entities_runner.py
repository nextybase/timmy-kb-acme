# SPDX-License-Identifier: GPL-3.0-only
# src/semantic/entities_runner.py
"""Runner additivo per scrivere entità area-aware in doc_entities.

Best effort: se SpaCy/mapping mancano, logga warning e non blocca il flusso.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, cast

from pipeline.exceptions import ConfigError
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
    base_dir: Path,
    raw_dir: Path,
    semantic_dir: Path,
    db_path: Path,
    logger: logging.Logger | None = None,
    max_per_area: int = 5,
    min_confidence: float = 0.4,
) -> dict[str, Any]:
    """Esegue tagging SpaCy+lexicon e salva in doc_entities (fail-soft)."""
    log = logger or LOG
    backend_env = (os.getenv("TAGS_NLP_BACKEND") or "").strip().lower()
    strict_spacy = backend_env == "spacy"
    workspace_root = base_dir
    try:
        cfg = load_semantic_config(workspace_root)
    except Exception as exc:  # pragma: no cover
        if strict_spacy:
            err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
            err_type = type(exc).__name__
            raise ConfigError(f"Config semantica non caricabile: {err_type}: {err_line}") from exc
        log.warning("semantic.entities.config_failed", extra={"error": str(exc)})
        return {"entities_written": 0}

    try:
        mapping = cfg.mapping or {}
        lexicon_entries = build_lexicon(mapping)
        lexicon = build_lexicon_map(lexicon_entries)
        if not lexicon:
            log.info(
                "semantic.entities.lexicon_empty",
                extra={"entries": len(lexicon_entries)},
            )
            return {"entities_written": 0}

        nlp = _load_spacy(cfg.spacy_model)
        matcher = make_phrase_matcher(nlp, lexicon)
    except Exception as exc:
        if strict_spacy:
            err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
            err_type = type(exc).__name__
            raise ConfigError(f"SpaCy non disponibile: {err_type}: {err_line}") from exc
        log.warning("semantic.entities.spacy_unavailable", extra={"error": str(exc)})
        return {"entities_written": 0}

    raw_dir = ensure_within_and_resolve(base_dir, raw_dir)
    db_path = ensure_within_and_resolve(base_dir, db_path)
    semantic_dir = ensure_within_and_resolve(base_dir, semantic_dir)
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(base_dir, db_path)

    hits_to_save: list[DocEntityHit] = []
    for pdf_path in iter_safe_pdfs(raw_dir):
        rel_uid = pdf_path.relative_to(base_dir).as_posix()
        try:
            text = _read_document_text(pdf_path)
        except Exception as exc:
            if strict_spacy:
                err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
                err_type = type(exc).__name__
                raise ConfigError(
                    f"Lettura PDF fallita: {err_type}: {err_line}",
                    file_path=pdf_path,
                ) from exc
            log.warning("semantic.entities.pdf_read_failed", extra={"file": str(pdf_path), "error": str(exc)})
            continue
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
        return {"entities_written": 0}

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
        if strict_spacy:
            err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
            err_type = type(exc).__name__
            raise ConfigError(
                f"Salvataggio doc_entities fallito: {err_type}: {err_line}",
                file_path=db_path,
            ) from exc
        log.warning("semantic.entities.save_failed", extra={"error": str(exc)})
        return {"entities_written": 0}
    log.info(
        "semantic.entities.saved",
        extra={
            "count": hits_count,
            "spacy_model": cfg.spacy_model,
            "slug": getattr(cfg, "slug", None),
        },
    )
    return {"entities_written": hits_count}
