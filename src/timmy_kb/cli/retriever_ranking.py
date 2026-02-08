# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import heapq
import math
import time
from itertools import tee
from typing import Any, Iterable, Mapping, Optional, Sequence

from pipeline.logging_utils import get_structured_logger
from timmy_kb.cli import retriever_throttle as throttle_mod
from timmy_kb.cli import retriever_validation as validation_mod

LOGGER = get_structured_logger("timmy_kb.retriever")

QueryParams = validation_mod.QueryParams
SearchResult = validation_mod.SearchResult
_deadline_exceeded = throttle_mod._deadline_exceeded


def _coerce_candidate_vector(*args, **kwargs):
    from timmy_kb.cli import retriever_embeddings as embeddings_mod

    return embeddings_mod._coerce_candidate_vector(*args, **kwargs)


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    """Calcola la similarità coseno tra due vettori numerici."""

    pairs_iter = ((float(x), float(y)) for x, y in zip(a, b, strict=False))
    stats_iter, calc_iter = tee(pairs_iter)

    count = 0
    max_abs = 0.0
    for x, y in stats_iter:
        ax = abs(x)
        ay = abs(y)
        if ax > max_abs:
            max_abs = ax
        if ay > max_abs:
            max_abs = ay
        count += 1

    if count == 0 or max_abs == 0.0:
        return 0.0

    try:
        import sys as _sys

        hi = math.sqrt(_sys.float_info.max / float(count)) * 0.99
        lo = math.sqrt(_sys.float_info.min) * 1.01
    except Exception:
        hi = 1.3e154
        lo = 1e-154

    if max_abs > hi:
        scale = hi / max_abs
    elif max_abs < lo:
        scale = lo / max_abs
    else:
        scale = 1.0

    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in calc_iter:
        sx = x * scale
        sy = y * scale
        dot += sx * sy
        na += sx * sx
        nb += sy * sy

    if na == 0.0 or nb == 0.0:
        return 0.0

    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0

    result = dot / denom
    if result > 1.0:
        return 1.0
    if result < -1.0:
        return -1.0
    return result


def _rank_candidates(
    query_vector: Sequence[float],
    candidates: Sequence[dict[str, Any]],
    k: int,
    *,
    deadline: Optional[float] = None,
    abort_if_deadline: bool = False,
) -> tuple[list[SearchResult], int, dict[str, int], float, int, bool]:
    """Restituisce (risultati, n_candidati_tot, stats, ms, valutati, budget_hit)."""
    stats: dict[str, int] = {"short": 0, "normalized": 0, "skipped": 0}
    total_candidates = len(candidates)
    evaluated = 0
    budget_hit = False
    t0 = time.time()
    top_k = max(0, int(k))
    results: list[SearchResult] = []

    if top_k > 0 and total_candidates > 0:
        if top_k >= total_candidates:
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for idx, cand in enumerate(candidates):
                if _deadline_exceeded(deadline):
                    budget_hit = True
                    break
                vec = _coerce_candidate_vector(cand.get("embedding"), idx=idx, stats=stats)
                if vec is None:
                    continue
                evaluated += 1
                score = float(cosine(query_vector, vec))
                scored.append(
                    (
                        score,
                        idx,
                        {
                            "content": cand["content"],
                            "meta": cand.get("meta", {}),
                            "score": score,
                        },
                    )
                )
            scored.sort(key=lambda t: (-t[0], t[1]))
            results = [item for _, _, item in scored[:top_k]]
        else:
            heap: list[tuple[tuple[float, int], dict[str, Any]]] = []
            for idx, cand in enumerate(candidates):
                if _deadline_exceeded(deadline):
                    budget_hit = True
                    break
                vec = _coerce_candidate_vector(cand.get("embedding"), idx=idx, stats=stats)
                if vec is None:
                    continue
                evaluated += 1
                score = float(cosine(query_vector, vec))
                item: SearchResult = {"content": cand["content"], "meta": cand.get("meta", {}), "score": score}
                key = (score, idx)
                if len(heap) < top_k:
                    heapq.heappush(heap, (key, item))
                else:
                    if key > heap[0][0]:
                        heapq.heapreplace(heap, (key, item))
            results = [item for _, item in sorted(heap, key=lambda t: (-t[0][0], t[0][1]))]

    elapsed_ms = (time.time() - t0) * 1000.0
    if abort_if_deadline and budget_hit:
        return results, total_candidates, stats, elapsed_ms, evaluated, budget_hit
    return results, total_candidates, stats, elapsed_ms, evaluated, budget_hit


def _log_retriever_metrics(
    params: QueryParams,
    total_ms: float,
    t_emb_ms: float,
    t_fetch_ms: float,
    t_score_sort_ms: float,
    candidates_count: int,
    evaluated_count: int,
    coerce_stats: Mapping[str, int],
) -> None:
    try:
        LOGGER.info(
            "retriever.metrics",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "k": int(params.k),
                "candidate_limit": int(params.candidate_limit),
                "candidates": int(candidates_count),
                "evaluated": int(evaluated_count),
                "ms": {
                    "total": float(total_ms),
                    "embed": float(t_emb_ms),
                    "fetch": float(t_fetch_ms),
                    "score_sort": float(t_score_sort_ms),
                },
                "coerce": {
                    "short": int(coerce_stats.get("short", 0)),
                    "normalized": int(coerce_stats.get("normalized", 0)),
                    "skipped": int(coerce_stats.get("skipped", 0)),
                },
            },
        )
    except Exception:
        LOGGER.info(
            (
                "search(): k=%s candidates=%s limit=%s total=%.1fms embed=%.1fms "
                "fetch=%.1fms score+sort=%.1fms evaluated=%s"
            ),
            params.k,
            candidates_count,
            params.candidate_limit,
            total_ms,
            t_emb_ms,
            t_fetch_ms,
            t_score_sort_ms,
            evaluated_count,
        )
