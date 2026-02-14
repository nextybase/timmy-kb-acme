# SPDX-License-Identifier: GPL-3.0-or-later
"""Servizi dedicati all'indicizzazione Markdown -> DB SQLite con embeddings."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pipeline.content_utils import build_chunk_records_from_markdown_files
from pipeline.embedding_utils import normalize_embeddings
from pipeline.exceptions import ConfigError
from pipeline.frontmatter_utils import dump_frontmatter as _shared_dump_frontmatter
from pipeline.frontmatter_utils import read_frontmatter as _read_fm
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, iter_safe_paths, sorted_paths
from pipeline.types import ChunkRecord
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from storage.kb_db import init_db as _init_kb_db
from storage.kb_db import insert_chunks as _insert_chunks

__all__ = ["list_content_markdown", "index_markdown_to_db"]


def list_content_markdown(book_dir: Path) -> List[Path]:
    """Elenca i Markdown 'di contenuto' in book_dir, escludendo README/SUMMARY."""
    return [
        path
        for path in sorted_paths(
            iter_safe_paths(book_dir, include_dirs=False, include_files=True, suffixes=(".md",)),
            base=book_dir,
        )
        if path.name.lower() not in {"readme.md", "summary.md"}
    ]


@dataclass(frozen=True)
class _CollectedMarkdown:
    contents: List[str]
    rel_paths: List[str]
    frontmatters: List[Dict[str, object]]
    skipped_io: int
    skipped_empty: int
    total_files: int


@dataclass(frozen=True)
class _EmbeddingResult:
    contents: List[str]
    rel_paths: List[str]
    frontmatters: List[Dict[str, object]]
    embeddings: List[List[float]]
    vectors_empty: int


def _collect_markdown_inputs(
    book_dir: Path,
    files: Sequence[Path],
    logger: logging.Logger,
    slug: str,
) -> _CollectedMarkdown:
    contents: List[str] = []
    rel_paths: List[str] = []
    frontmatters: List[Dict[str, object]] = []
    skipped_io = 0
    skipped_empty = 0

    for candidate in files:
        try:
            meta, body = _read_fm(book_dir, candidate, encoding="utf-8", use_cache=True)
        except UnicodeError:
            raise
        except Exception as exc:  # noqa: BLE001 - vogliamo loggare tutti i casi
            logger.warning(
                "semantic.index.read_failed",
                extra={"slug": slug, "file_path": str(candidate), "error": str(exc)},
            )
            skipped_io += 1
            continue

        payload = (body or "").lstrip("\ufeff").strip()
        if not payload and meta:
            payload = _shared_dump_frontmatter(meta).strip()
        if not payload:
            logger.info(
                "semantic.index.skip_empty_file",
                extra={"slug": slug, "file_path": str(candidate)},
            )
            skipped_empty += 1
            continue

        contents.append(payload)
        rel_paths.append(candidate.relative_to(book_dir).as_posix())
        frontmatters.append(dict(meta or {}))

    return _CollectedMarkdown(
        contents=contents,
        rel_paths=rel_paths,
        frontmatters=frontmatters,
        skipped_io=skipped_io,
        skipped_empty=skipped_empty,
        total_files=len(files),
    )


def _collect_chunk_records(
    chunk_records: Sequence[ChunkRecord],
    logger: logging.Logger,
    slug: str,
) -> _CollectedMarkdown:
    """Costruisce i payload a partire dai ChunkRecord forniti."""

    contents: List[str] = []
    rel_paths: List[str] = []
    frontmatters: List[Dict[str, object]] = []
    skipped_empty = 0

    for record in chunk_records:
        payload = (record.get("text") or "").strip()
        if not payload:
            skipped_empty += 1
            logger.info(
                "semantic.index.skip_empty_file",
                extra={"slug": slug, "file_path": record["source_path"]},
            )
            continue
        contents.append(payload)
        rel_paths.append(record["source_path"])
        meta = dict(record.get("metadata") or {})
        meta.setdefault("chunk_index", record["chunk_index"])
        meta.setdefault("created_at", record["created_at"])
        meta.setdefault("chunk_id", record["id"])
        meta.setdefault("source_path", record["source_path"])
        meta.setdefault("slug", slug)
        frontmatters.append(meta)

    return _CollectedMarkdown(
        contents=contents,
        rel_paths=rel_paths,
        frontmatters=frontmatters,
        skipped_io=0,
        skipped_empty=skipped_empty,
        total_files=len(chunk_records),
    )


def _compute_embeddings_for_markdown(
    collected: _CollectedMarkdown,
    embeddings_client: _EmbeddingsClient,
    logger: logging.Logger,
    slug: str,
) -> Tuple[Optional[_EmbeddingResult], int]:
    if not collected.contents:
        return None, 0

    try:
        vectors_raw = embeddings_client.embed_texts(collected.contents)
    except Exception as exc:  # noqa: BLE001 - surface per telemetria
        logger.error(
            "semantic.index.embedding_error",
            extra={
                "slug": slug,
                "error": str(exc),
                "count": len(collected.contents),
                "files": collected.rel_paths[:5],
                "provider": getattr(embeddings_client, "__class__", type("x", (), {})).__name__,
            },
        )
        return None, 0

    vectors = normalize_embeddings(vectors_raw)
    vectors_empty = 0

    if len(vectors) == 0:
        logger.warning("semantic.index.no_embeddings", extra={"slug": slug, "count": 0})
        return None, 0

    contents = list(collected.contents)
    rel_paths = list(collected.rel_paths)
    frontmatters = list(collected.frontmatters)

    original_contents_len = len(contents)
    original_embeddings_len = len(vectors)

    if original_embeddings_len != original_contents_len:
        logger.warning(
            "semantic.index.mismatched_embeddings",
            extra={
                "slug": slug,
                "embeddings": original_embeddings_len,
                "contents": original_contents_len,
            },
        )
        min_len = min(original_embeddings_len, original_contents_len)
        dropped_mismatch = (original_contents_len - min_len) + (original_embeddings_len - min_len)
        if dropped_mismatch > 0:
            logger.info(
                "semantic.index.embedding_pruned",
                extra={
                    "slug": slug,
                    "cause": "mismatch",
                    "dropped": int(dropped_mismatch),
                    "kept": int(min_len),
                    "contents": int(original_contents_len),
                    "embeddings": int(original_embeddings_len),
                },
            )
        vectors_empty += max(0, dropped_mismatch)
        contents = contents[:min_len]
        rel_paths = rel_paths[:min_len]
        vectors = vectors[:min_len]
        frontmatters = frontmatters[:min_len]

    original_candidate_count = len(contents)
    filtered_contents: List[str] = []
    filtered_paths: List[str] = []
    filtered_vectors: List[List[float]] = []
    filtered_frontmatters: List[Dict[str, object]] = []

    for text, rel_name, vector, meta in zip(contents, rel_paths, vectors, frontmatters, strict=False):
        if len(vector) == 0:
            continue
        filtered_contents.append(text)
        filtered_paths.append(rel_name)
        filtered_vectors.append(list(vector))
        filtered_frontmatters.append(meta)

    dropped_empty = original_candidate_count - len(filtered_contents)
    if dropped_empty > 0 and len(filtered_contents) == 0:
        logger.warning(
            "semantic.index.first_embedding_empty",
            extra={"slug": slug, "cause": "empty_embedding"},
        )
        logger.warning(
            "semantic.index.all_embeddings_empty",
            extra={"event": "semantic.index.all_embeddings_empty", "slug": slug, "count": len(vectors)},
        )
        vectors_empty += max(0, dropped_empty)
        return None, vectors_empty

    if dropped_empty > 0:
        logger.info(
            "semantic.index.embedding_pruned",
            extra={
                "slug": slug,
                "cause": "empty_embedding",
                "dropped": int(dropped_empty),
                "kept": int(len(filtered_contents)),
                "candidates": int(original_candidate_count),
            },
        )
        vectors_empty += max(0, dropped_empty)

    return (
        _EmbeddingResult(
            contents=filtered_contents,
            rel_paths=filtered_paths,
            frontmatters=filtered_frontmatters,
            embeddings=filtered_vectors,
            vectors_empty=vectors_empty,
        ),
        vectors_empty,
    )


def _log_index_skips(
    logger: logging.Logger,
    slug: str,
    *,
    skipped_io: int,
    skipped_empty: int,
    vectors_empty: int,
) -> None:
    logger.info(
        "semantic.index.skips",
        extra={
            "slug": slug,
            "skipped_io": skipped_io,
            "skipped_no_text": skipped_empty,
            "vectors_empty": vectors_empty,
        },
    )


def _build_lineage_for_markdown(*, slug: str, scope: str, version: str, rel_name: str) -> Dict[str, object]:
    source_id = f"{slug}:{scope}:{version}:{rel_name}"
    chunk_hash = hashlib.sha256(f"{source_id}:0".encode("utf-8")).hexdigest()
    return {
        "source_id": source_id,
        "chunks": [
            {
                "chunk_index": 0,
                "chunk_id": chunk_hash,
                "embedding_id": chunk_hash,
            }
        ],
    }


def _persist_markdown_embeddings(
    embeddings_result: _EmbeddingResult,
    *,
    scope: str,
    slug: str,
    db_path: Optional[Path],
    logger: logging.Logger,
) -> int:
    from datetime import datetime as _dt

    inserted_total = 0
    version = _dt.utcnow().strftime("%Y%m%d")
    batch_chunks: list[tuple[str, dict[str, object], str, list[float]]] = []
    for rel_name, vector, body, meta in zip(
        embeddings_result.rel_paths,
        embeddings_result.embeddings,
        embeddings_result.contents,
        embeddings_result.frontmatters,
        strict=False,
    ):
        payload_meta: Dict[str, object] = {"file": rel_name}
        if isinstance(meta, dict):
            filtered = {k: v for k, v in meta.items() if v not in (None, "", [], {})}
            payload_meta.update(filtered)
        if not isinstance(payload_meta.get("lineage"), dict):
            payload_meta["lineage"] = _build_lineage_for_markdown(
                slug=slug,
                scope=scope,
                version=version,
                rel_name=rel_name,
            )
        batch_chunks.append(
            (
                rel_name,
                payload_meta,
                body,
                list(vector),
            )
        )

    for rel_name, payload_meta, body, vector in batch_chunks:
        # Arricchisce i metadati con campi ER-aware se presenti
        if isinstance(payload_meta, dict):
            entity = payload_meta.get("entity")
            area = payload_meta.get("area")
            relation_hints = payload_meta.get("relation_hints")
            if entity:
                payload_meta["entity"] = entity
            if area:
                payload_meta["area"] = area
            if relation_hints:
                payload_meta["relation_hints"] = relation_hints
            lineage = payload_meta.get("lineage")
        else:
            lineage = None
        if isinstance(lineage, dict):
            source_id = lineage.get("source_id")
            chunk = (lineage.get("chunks") or [{}])[0]
            logger.info(
                "semantic.input.received",
                extra={
                    "slug": slug,
                    "scope": scope,
                    "source_id": source_id,
                    "source_path": rel_name,
                    "content_type": "markdown",
                },
            )
            logger.info(
                "semantic.lineage.chunk_created",
                extra={
                    "slug": slug,
                    "scope": scope,
                    "path": rel_name,
                    "source_id": source_id,
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_index": chunk.get("chunk_index"),
                },
            )
        inserted_total += _insert_chunks(
            slug=slug,
            scope=scope,
            path=rel_name,
            version=version,
            meta_dict=payload_meta,
            chunks=[body],
            embeddings=[vector],
            db_path=db_path,
            ensure_schema=False,
        )
        if isinstance(lineage, dict):
            logger.info(
                "semantic.lineage.embedding_registered",
                extra={
                    "slug": slug,
                    "scope": scope,
                    "path": rel_name,
                    "source_id": lineage.get("source_id"),
                    "version": version,
                    "embedding_count": 1,
                },
            )
            override = lineage.get("hilt_override")
            if isinstance(override, dict):
                logger.info(
                    "semantic.lineage.hilt_override",
                    extra={
                        "slug": slug,
                        "source_id": lineage.get("source_id"),
                        "chunk_id": (lineage.get("chunks") or [{}])[0].get("chunk_id"),
                        "operator_id": override.get("operator_id"),
                        "reason": override.get("reason"),
                    },
                )

    logger.info(
        "semantic.index.inserted",
        extra={"slug": slug, "inserted": inserted_total},
    )
    return inserted_total


def index_markdown_to_db(
    *,
    repo_root_dir: Path,
    book_dir: Path,
    slug: str,
    logger: logging.Logger,
    scope: str,
    embeddings_client: _EmbeddingsClient,
    db_path: Optional[Path],
    chunk_records: Sequence[ChunkRecord] | None = None,
) -> int:
    """Indicizza i Markdown presenti in `book_dir` nel DB con embeddings."""
    if db_path is None:
        raise ConfigError(
            "db_path must be provided explicitly via WorkspaceLayout / ClientContext. "
            "Implicit CWD-based resolution is forbidden.",
            slug=slug,
        )
    ensure_within(repo_root_dir, book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    start_ts = time.perf_counter()

    collected: _CollectedMarkdown
    if chunk_records is not None:
        total_files = len(chunk_records)
        collected = _collect_chunk_records(chunk_records, logger, slug)
        logger.info(
            "semantic.index.collect.start",
            extra={"slug": slug, "files": total_files},
        )
        logger.info(
            "semantic.index.collect.done",
            extra={
                "slug": slug,
                "files": total_files,
                "usable": len(collected.contents),
                "skipped_io": collected.skipped_io,
                "skipped_no_text": collected.skipped_empty,
            },
        )
    else:
        files = list_content_markdown(book_dir)
        if not files:
            with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as phase:
                logger.info("semantic.index.no_files", extra={"slug": slug, "book_dir": str(book_dir)})
                try:
                    phase.set_artifacts(0)
                except Exception:
                    phase.set_artifacts(None)
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "semantic.index.done",
                extra={"slug": slug, "ms": duration_ms, "artifacts": {"inserted": 0, "files": 0}},
            )
            return 0
        total_files = len(files)
        logger.info(
            "semantic.index.collect.start",
            extra={"slug": slug, "files": total_files},
        )
        chunk_records = build_chunk_records_from_markdown_files(
            slug,
            files,
            chunking="heading",
            perimeter_root=book_dir,
        )
        collected = _collect_chunk_records(
            chunk_records,
            logger,
            slug,
        )
        used_paths = {rel for rel in collected.rel_paths}
        for path in files:
            rel_path = path.relative_to(book_dir).as_posix()
            if rel_path not in used_paths:
                logger.info(
                    "semantic.index.skip_empty_file",
                    extra={"slug": slug, "file_path": rel_path},
                )
        logger.info(
            "semantic.index.collect.done",
            extra={
                "slug": slug,
                "files": total_files,
                "usable": len(collected.contents),
                "skipped_io": collected.skipped_io,
                "skipped_no_text": collected.skipped_empty,
            },
        )

    if not collected.contents:
        with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as phase:
            logger.info("semantic.index.no_valid_contents", extra={"slug": slug, "book_dir": str(book_dir)})
            _log_index_skips(
                logger,
                slug,
                skipped_io=collected.skipped_io,
                skipped_empty=collected.skipped_empty,
                vectors_empty=0,
            )
            try:
                phase.set_artifacts(0)
            except Exception:
                phase.set_artifacts(None)
        duration_ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "semantic.index.done",
            extra={"slug": slug, "ms": duration_ms, "artifacts": {"inserted": 0, "files": total_files}},
        )
        return 0

    with phase_scope(logger, stage="index_markdown_to_db", customer=slug) as phase:
        try:
            _init_kb_db(db_path)
        except Exception as exc:  # noqa: BLE001 - vogliamo contesto completo
            raise ConfigError(
                f"Inizializzazione DB fallita: {exc}",
                slug=slug,
                file_path=str(Path(db_path).resolve()),
            ) from exc

        logger.info(
            "semantic.index.embed.start",
            extra={"slug": slug, "count": len(collected.contents)},
        )
        embeddings_result, vectors_empty = _compute_embeddings_for_markdown(
            collected,
            embeddings_client,
            logger,
            slug,
        )
        if embeddings_result is None:
            _log_index_skips(
                logger,
                slug,
                skipped_io=collected.skipped_io,
                skipped_empty=collected.skipped_empty,
                vectors_empty=vectors_empty,
            )
            try:
                phase.set_artifacts(0)
            except Exception:
                phase.set_artifacts(None)
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            logger.info(
                "semantic.index.done",
                extra={"slug": slug, "ms": duration_ms, "artifacts": {"inserted": 0, "files": total_files}},
            )
            return 0

        logger.info(
            "semantic.index.embed.done",
            extra={"slug": slug, "count": len(embeddings_result.contents)},
        )

        _log_index_skips(
            logger,
            slug,
            skipped_io=collected.skipped_io,
            skipped_empty=collected.skipped_empty,
            vectors_empty=embeddings_result.vectors_empty,
        )

        logger.info(
            "semantic.index.persist.start",
            extra={"slug": slug, "files": len(embeddings_result.contents)},
        )
        inserted_total = _persist_markdown_embeddings(
            embeddings_result,
            scope=scope,
            slug=slug,
            db_path=db_path,
            logger=logger,
        )
        logger.info(
            "semantic.index.persist.done",
            extra={"slug": slug, "inserted": inserted_total, "files": len(embeddings_result.contents)},
        )

        duration_ms = int((time.perf_counter() - start_ts) * 1000)
        logger.info(
            "semantic.index.done",
            extra={
                "slug": slug,
                "ms": duration_ms,
                "artifacts": {"inserted": inserted_total, "files": len(embeddings_result.contents)},
            },
        )
        try:
            phase.set_artifacts(inserted_total)
        except Exception:
            phase.set_artifacts(None)
        return inserted_total
