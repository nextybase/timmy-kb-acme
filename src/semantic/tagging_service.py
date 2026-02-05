# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/tagging_service.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, TypedDict, cast

from pipeline.exceptions import ConfigError, PathTraversalError
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, ensure_within_and_resolve
from pipeline.workspace_layout import WorkspaceLayout
from semantic.auto_tagger import extract_semantic_candidates
from semantic.auto_tagger import render_tags_csv as _render_tags_csv
from semantic.config import load_semantic_config as _load_semantic_config
from semantic.normalizer import normalize_tags as _normalize_tags
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.types import SemanticContextProtocol as ClientContextType
from storage.tags_store import DocEntityRecord, derive_db_path_from_yaml_path
from storage.tags_store import ensure_schema_v2 as _ensure_tags_schema_v2
from storage.tags_store import get_conn as _get_tags_conn
from storage.tags_store import save_doc_entities as _save_doc_entities


class CandidateMeta(TypedDict, total=False):
    tags: Sequence[str]
    sources: Mapping[str, Any]
    score: Mapping[str, Any]
    entities: Sequence[Any]
    keyphrases: Sequence[Any]


def _collect_doc_entities(candidates: Mapping[str, CandidateMeta]) -> List[DocEntityRecord]:
    """Estrae le entity NLP dai metadati dei candidati in una lista flat."""

    doc_entities: List[DocEntityRecord] = []
    for rel_path, meta in candidates.items():
        sources: Mapping[str, Any] = meta.get("sources") or {}
        spacy_src: Mapping[str, Any] = cast(Mapping[str, Any], sources.get("spacy") or {})
        areas: Mapping[str, Sequence[str]] = cast(Mapping[str, Sequence[str]], spacy_src.get("areas") or {})
        score_map: Mapping[str, Any] = meta.get("score") or {}
        rel_uid = Path(rel_path).as_posix()
        for area_key, ent_list in areas.items():
            for entity_id in ent_list or []:
                key = f"{area_key}:{entity_id}"
                try:
                    confidence = float(score_map.get(key, 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                if confidence <= 0.0:
                    continue
                doc_entities.append(
                    DocEntityRecord(
                        doc_uid=rel_uid,
                        area_key=str(area_key),
                        entity_id=str(entity_id),
                        confidence=confidence,
                        origin="spacy",
                        status="suggested",
                    )
                )
    return doc_entities


def _load_folder_terms(tags_db_path: Path, *, slug: str | None = None) -> Dict[str, List[str]]:
    """Ritorna i top-term per cartella dal DB NLP (se presente)."""

    folder_terms: Dict[str, List[str]] = {}
    if not tags_db_path.exists():
        raise ConfigError(
            "tags.db mancante per arricchimento top-terms.",
            slug=slug,
            file_path=tags_db_path,
        )

    try:
        _ensure_tags_schema_v2(str(tags_db_path))
        with _get_tags_conn(str(tags_db_path)) as conn:
            rows = conn.execute(
                """
                SELECT f.path AS folder_path, t.canonical AS term, SUM(ft.weight) AS weight
                FROM folder_terms ft
                JOIN folders f ON f.id = ft.folder_id
                JOIN terms   t ON t.id = ft.term_id
                GROUP BY f.path, t.canonical
                ORDER BY f.path, weight DESC
                """
            ).fetchall()
    except Exception as exc:  # pragma: no cover - fail-fast wrapping
        raise ConfigError("Errore accesso tags.db", slug=slug, file_path=tags_db_path) from exc
    for row in rows:
        folder_path = str(row["folder_path"] or "")
        canonical = str(row["term"] or "").strip()
        if not canonical:
            continue
        rel_folder = folder_path[11:] if folder_path.startswith("normalized/") else folder_path
        rel_folder = rel_folder.strip("/")
        folder_terms.setdefault(rel_folder, []).append(canonical)
    return folder_terms


def _apply_folder_terms(
    candidates: Mapping[str, CandidateMeta],
    folder_terms: Mapping[str, Sequence[str]],
) -> Dict[str, CandidateMeta]:
    """Arricchisce i metadati candidati con i top-term per cartella."""

    enriched_candidates: Dict[str, CandidateMeta] = {}
    max_terms = 16
    for rel_path, meta in candidates.items():
        rel_folder = Path(rel_path).parent.as_posix()
        rel_folder = "" if rel_folder == "." else rel_folder
        nlp_tags = folder_terms.get(rel_folder)
        if not nlp_tags:
            enriched_candidates[rel_path] = cast(CandidateMeta, dict(meta))
            continue
        existing = list(meta.get("tags") or [])
        seen_lower = {str(tag).strip().lower() for tag in existing if str(tag).strip()}
        enriched: list[str] = list(existing)
        for term in nlp_tags:
            term_norm = str(term).strip()
            if not term_norm:
                continue
            key = term_norm.lower()
            if key in seen_lower:
                continue
            enriched.append(term_norm)
            seen_lower.add(key)
            if len(enriched) >= max_terms:
                break
        updated = cast(CandidateMeta, dict(meta))
        if enriched:
            updated["tags"] = enriched
        enriched_candidates[rel_path] = updated
    return enriched_candidates


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    """Costruisce `tags_raw.csv` dal workspace corrente applicando arricchimento NLP (DB + Spacy)."""
    if getattr(context, "repo_root_dir", None) is None:
        raise ConfigError(
            "Context privo di repo_root_dir: impossibile risolvere WorkspaceLayout.",
            slug=slug,
        )
    layout = WorkspaceLayout.from_context(cast(Any, context))
    repo_root_dir = layout.repo_root_dir
    perimeter_root = repo_root_dir
    normalized_dir = layout.normalized_dir
    semantic_dir = layout.semantic_dir
    csv_path = semantic_dir / "tags_raw.csv"

    ensure_within(perimeter_root, normalized_dir)
    ensure_within(perimeter_root, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    with phase_scope(logger, stage="build_tags_csv", customer=slug) as m:
        semantic_dir.mkdir(parents=True, exist_ok=True)
        cfg = _load_semantic_config(context)
        candidates = extract_semantic_candidates(normalized_dir, cfg)
        candidates = _normalize_tags(candidates, cfg.mapping)
        doc_entities = _collect_doc_entities(candidates)

        # Arricchimento con top-terms NLP (se disponibili in tags.db)
        tags_db_path: Path | None = None
        try:
            tags_db_path = Path(derive_db_path_from_yaml_path(semantic_dir / "tags_reviewed.yaml"))
            tags_db_path = ensure_within_and_resolve(semantic_dir, tags_db_path)
            folder_terms = _load_folder_terms(tags_db_path, slug=slug)
            if folder_terms:
                candidates = _apply_folder_terms(candidates, folder_terms)
            if doc_entities:
                _save_doc_entities(tags_db_path, doc_entities)
        except PathTraversalError:
            raise
        except Exception as exc:
            err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
            err_type = type(exc).__name__
            logger.exception(
                "semantic.tags_csv.enrichment_failed",
                extra={
                    "slug": slug,
                    "error": str(exc),
                    "tags_db": str(tags_db_path) if tags_db_path else None,
                },
            )
            raise ConfigError(
                f"Arricchimento tag fallito: {err_type}: {err_line}",
                slug=slug,
                file_path=tags_db_path,
            ) from exc

        _render_tags_csv(candidates, csv_path, perimeter_root=perimeter_root)
        count = len(candidates)
        logger.info(
            "semantic.tags_csv.built",
            extra={"slug": slug, "file_path": str(csv_path), "count": count},
        )
        _write_tagging_readme(semantic_dir, logger)
        try:
            m.set_artifacts(count)
        except Exception as exc:
            logger.warning("semantic.tags_csv.artifacts_missing", extra={"slug": slug, "error": str(exc)})
            m.set_artifacts(None)
    return csv_path
