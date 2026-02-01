# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from explainability.serialization import safe_write_manifest
from pipeline.exceptions import PipelineError
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient
from timmy_kb.cli import retriever_throttle as throttle_mod
from timmy_kb.cli import retriever_validation as validation_mod

LOGGER = get_structured_logger("timmy_kb.retriever")

QueryParams = validation_mod.QueryParams
ThrottleSettings = throttle_mod.ThrottleSettings


def _log_logging_failure(event: str, exc: Exception) -> None:
    payload = {"event": event, "error": repr(exc)}
    try:
        LOGGER.warning("retriever.log_failed", extra=payload)
    except Exception:
        logging.getLogger("timmy_kb.retriever").warning(
            "retriever.log_failed event=%s error=%r",
            event,
            exc,
        )


def _extract_lineage_for_logs(meta: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    if not isinstance(meta, Mapping):
        return None, None
    lineage = meta.get("lineage")
    if not isinstance(lineage, Mapping):
        return None, None
    source_id = lineage.get("source_id") if isinstance(lineage.get("source_id"), str) else None
    chunk_id = None
    chunks = lineage.get("chunks")
    if isinstance(chunks, Sequence) and chunks:
        first = chunks[0]
        if isinstance(first, Mapping):
            cid = first.get("chunk_id")
            if isinstance(cid, str):
                chunk_id = cid
    return source_id, chunk_id


def _build_evidence_ids(scored_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    evidence_ids: list[dict[str, Any]] = []
    for idx, item in enumerate(scored_items):
        meta = item.get("meta", {}) if isinstance(item, Mapping) else {}
        source_id, chunk_id = _extract_lineage_for_logs(meta)
        evidence_ids.append(
            {
                "rank": idx + 1,
                "score": float(item.get("score", 0.0)) if isinstance(item, Mapping) else 0.0,
                "source_id": source_id,
                "chunk_id": chunk_id,
            }
        )
    return evidence_ids


def _log_evidence_selected(
    params: QueryParams,
    scored_items: Sequence[Mapping[str, Any]],
    evidence_ids: Sequence[Mapping[str, Any]],
    *,
    response_id: str | None,
    budget_hit: bool,
) -> None:
    try:
        LOGGER.info(
            "retriever.evidence.selected",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "response_id": response_id,
                "k": int(params.k),
                "selected_count": len(scored_items),
                "budget_hit": bool(budget_hit),
                "evidence_ids": list(evidence_ids),
            },
        )
    except Exception as exc:
        _log_logging_failure("retriever.evidence.selected", exc)


def _write_manifest_if_configured(
    params: QueryParams,
    scored_items: Sequence[Mapping[str, Any]],
    *,
    response_id: str | None,
    embeddings_client: EmbeddingsClient,
    embedding_model: str | None,
    explain_base_dir: Path | None,
    throttle_cfg: ThrottleSettings | None,
    candidates_count: int,
    evaluated_count: int,
    t_emb_ms: float,
    t_fetch_ms: float,
    t_score_sort_ms: float,
    total_ms: float,
    budget_hit: bool,
    evidence_ids: Sequence[Mapping[str, Any]],
) -> None:
    if not explain_base_dir or not response_id:
        return
    manifest: dict[str, Any] = {
        "response_id": response_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slug": params.slug,
        "scope": params.scope,
        "query": params.query,
        "retriever_params": {
            "k": int(params.k),
            "candidate_limit": int(params.candidate_limit),
            "latency_budget_ms": int(throttle_cfg.latency_budget_ms) if throttle_cfg else None,
        },
        "model": {
            "embedding_model": embedding_model
            or getattr(embeddings_client, "model", None)
            or getattr(embeddings_client, "embedding_model", None)
        },
        "evidence": [
            {
                "rank": idx + 1,
                "score": float(item.get("score", 0.0)) if isinstance(item, Mapping) else 0.0,
                "source_id": evidence_ids[idx].get("source_id"),
                "chunk_id": evidence_ids[idx].get("chunk_id"),
                "path": (item.get("meta", {}) or {}).get("path") if isinstance(item, Mapping) else None,
                "snippet": None,
            }
            for idx, item in enumerate(scored_items)
        ],
        "metrics": {
            "candidates_loaded": int(candidates_count),
            "evaluated": int(evaluated_count),
            "timings_ms": {
                "total": float(total_ms),
                "embed": float(t_emb_ms),
                "fetch": float(t_fetch_ms),
                "score_sort": float(t_score_sort_ms),
            },
        },
        "lineage_refs": [{"source_id": e.get("source_id"), "chunk_id": e.get("chunk_id")} for e in evidence_ids],
        "flags": {"budget_hit": bool(budget_hit)},
    }
    expected_path = Path(explain_base_dir) / f"{response_id}.json"
    try:
        manifest_path = safe_write_manifest(manifest, output_dir=explain_base_dir, response_id=response_id)
    except Exception as exc:
        try:
            LOGGER.error(
                "retriever.response.manifest.write_failed",
                extra={
                    "slug": params.slug,
                    "response_id": response_id,
                    "output_path": str(expected_path),
                    "error": repr(exc),
                },
            )
        except Exception as log_exc:
            _log_logging_failure("retriever.response.manifest.write_failed", log_exc)
        raise PipelineError(
            "Manifest explainability non scritto.",
            slug=params.slug,
            file_path=str(expected_path),
        ) from exc
    try:
        LOGGER.info(
            "retriever.response.manifest",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "response_id": response_id,
                "manifest_path": str(manifest_path),
                "evidence_ids": list(evidence_ids),
                "k": int(params.k),
                "selected_count": len(scored_items),
            },
        )
    except Exception as exc:
        _log_logging_failure("retriever.response.manifest", exc)
