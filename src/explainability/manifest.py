# SPDX-License-Identifier: GPL-3.0-or-later
"""Strutture dati per il manifest di risposta (explainability per-risposta).

Nota: nessun I/O o logging qui; il manifest viene costruito in memoria e
può essere serializzato o loggato dai call-site che lo usano.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping, Optional, Sequence, TypedDict

if TYPE_CHECKING:
    from timmy_kb.cli.retriever import QueryParams, SearchResult

SNIPPET_MAX_LEN = 200


class ResponseEvidence(TypedDict, total=False):
    rank: int
    score: float
    source_id: Optional[str]
    chunk_id: Optional[str]
    path: Optional[str]
    snippet: Optional[str]


class ResponseRetrieverParams(TypedDict, total=False):
    k: int
    candidate_limit: int
    latency_budget_ms: Optional[int]
    coerce_stats: Mapping[str, int]


class ResponseModelInfo(TypedDict, total=False):
    embedding_model: Optional[str]
    generator_model: Optional[str]


class ResponseTimings(TypedDict, total=False):
    total: Optional[float]
    embed: Optional[float]
    fetch: Optional[float]
    score_sort: Optional[float]


class ResponseMetrics(TypedDict, total=False):
    candidates_loaded: int
    evaluated: int
    timings_ms: ResponseTimings


class ResponseFlags(TypedDict, total=False):
    low_confidence: bool
    budget_hit: bool


class ResponseLineageRef(TypedDict, total=False):
    source_id: Optional[str]
    chunk_id: Optional[str]


class ResponseManifest(TypedDict, total=False):
    response_id: str
    timestamp: str
    slug: str
    scope: Optional[str]
    query: str
    retriever_params: ResponseRetrieverParams
    model: ResponseModelInfo
    evidence: list[ResponseEvidence]
    metrics: ResponseMetrics
    lineage_refs: list[ResponseLineageRef]
    flags: ResponseFlags


def _extract_lineage(meta: Mapping[str, Any] | None) -> ResponseLineageRef:
    lineage = None
    if meta:
        lineage = meta.get("lineage")
    if not isinstance(lineage, Mapping):
        return {"source_id": None, "chunk_id": None}
    source_id = lineage.get("source_id")
    chunk_id = None
    chunks = lineage.get("chunks")
    if isinstance(chunks, Sequence) and chunks:
        first = chunks[0]
        if isinstance(first, Mapping):
            chunk_id_val = first.get("chunk_id")
            if isinstance(chunk_id_val, str):
                chunk_id = chunk_id_val
    return {
        "source_id": source_id if isinstance(source_id, str) else None,
        "chunk_id": chunk_id,
    }


def _extract_path(meta: Mapping[str, Any] | None, lineage: ResponseLineageRef) -> Optional[str]:
    if meta:
        path_val = meta.get("path") or meta.get("file_path")
        if isinstance(path_val, str) and path_val.strip():
            return path_val
    return lineage.get("chunk_id")


def _make_snippet(content: Any, *, max_len: int = SNIPPET_MAX_LEN) -> Optional[str]:
    if not isinstance(content, str):
        return None
    if not content:
        return None
    if max_len <= 0:
        return content
    return content[:max_len]


def _coerce_stats(stats: Mapping[str, int] | None) -> Mapping[str, int]:
    if not stats:
        return {}
    clean: MutableMapping[str, int] = {}
    for key, value in stats.items():
        try:
            clean[key] = int(value)
        except Exception:
            continue
    return clean


def build_response_manifest(
    results: Sequence["SearchResult"],
    params: "QueryParams",
    response_id: str,
    slug: str,
    scope: str | None = None,
    *,
    coerce_stats: Mapping[str, int] | None = None,
    timings_ms: Mapping[str, float] | None = None,
    embedding_model: str | None = None,
    generator_model: str | None = None,
    budget_hit: bool | None = None,
    low_confidence: bool | None = None,
    candidates_loaded: int | None = None,
    evaluated: int | None = None,
    snippet_max_len: int = SNIPPET_MAX_LEN,
) -> ResponseManifest:
    """Costruisce un manifest per-risposta senza I/O o logging."""

    evidences: list[ResponseEvidence] = []
    lineage_refs: list[ResponseLineageRef] = []
    for idx, res in enumerate(results):
        meta = res.get("meta", {}) if isinstance(res, Mapping) else {}
        lineage = _extract_lineage(meta if isinstance(meta, Mapping) else {})
        lineage_refs.append(lineage)
        evidence: ResponseEvidence = {
            "rank": idx + 1,
            "score": float(res.get("score", 0.0)) if isinstance(res, Mapping) else 0.0,
            "source_id": lineage.get("source_id"),
            "chunk_id": lineage.get("chunk_id"),
            "path": _extract_path(meta if isinstance(meta, Mapping) else {}, lineage),
            "snippet": _make_snippet(res.get("content") if isinstance(res, Mapping) else None, max_len=snippet_max_len),
        }
        evidences.append(evidence)

    retr_params: ResponseRetrieverParams = {
        "k": int(params.k),
        "candidate_limit": int(params.candidate_limit),
        "latency_budget_ms": getattr(params, "latency_budget_ms", None),
    }
    if coerce_stats:
        retr_params["coerce_stats"] = _coerce_stats(coerce_stats)

    metrics: ResponseMetrics = {
        "candidates_loaded": int(candidates_loaded if candidates_loaded is not None else len(results)),
        "evaluated": int(evaluated if evaluated is not None else len(results)),
        "timings_ms": {},
    }
    if timings_ms:
        timings: ResponseTimings = {}
        for key in ("total", "embed", "fetch", "score_sort"):
            if key in timings_ms:
                try:
                    timings[key] = float(timings_ms[key])
                except Exception:
                    continue
        metrics["timings_ms"] = timings

    flags: ResponseFlags = {}
    if budget_hit is not None:
        flags["budget_hit"] = bool(budget_hit)
    if low_confidence is not None:
        flags["low_confidence"] = bool(low_confidence)

    manifest: ResponseManifest = {
        "response_id": response_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "scope": scope,
        "query": params.query,
        "retriever_params": retr_params,
        "model": {
            "embedding_model": embedding_model,
            "generator_model": generator_model,
        },
        "evidence": evidences,
        "metrics": metrics,
        "lineage_refs": lineage_refs,
        "flags": flags,
    }
    return manifest
