# SPDX-License-Identifier: GPL-3.0-or-later
# src/retriever.py
"""Utility di ricerca basata su embedding per la Timmy KB.

Funzioni esposte:
- cosine(a, b) -> float
- retrieve_candidates(params) -> list[dict]
- search(params, embeddings_client) -> list[SearchResult]
- with_config_candidate_limit(params, config) -> params
- choose_limit_for_budget(budget_ms) -> int
- with_config_or_budget(params, config) -> params
- search_with_config(params, config, embeddings_client) -> list[SearchResult]
- preview_effective_candidate_limit(params, config)
  -> (limit:int, source:str, budget_ms:int)

Design:
- Carica fino a `candidate_limit` candidati da SQLite (default: 4000).
- Calcola la similarità coseno in Python sui candidati.
- Restituisce i top-k come dict con: content, meta, score.
"""

from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import MISSING, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypedDict

from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from pipeline.logging_utils import get_structured_logger as _get_structured_logger
from semantic.types import EmbeddingsClient
from storage.kb_db import fetch_candidates
from timmy_kb.cli import retriever_embeddings as embeddings_mod
from timmy_kb.cli import retriever_errors as retriever_errors_mod
from timmy_kb.cli import retriever_logging as retriever_logging_mod
from timmy_kb.cli import retriever_manifest as manifest_mod
from timmy_kb.cli import retriever_ranking as ranking_mod
from timmy_kb.cli import retriever_throttle as throttle_mod
from timmy_kb.cli import retriever_validation as validation_mod
from timmy_kb.cli.retriever_ranking import _rank_candidates, cosine
from timmy_kb.cli.retriever_throttle import ThrottleSettings
from timmy_kb.cli.retriever_validation import MAX_CANDIDATE_LIMIT, MIN_CANDIDATE_LIMIT, QueryParams, SearchResult

LOGGER = retriever_logging_mod.LOGGER
_FALLBACK_LOG = retriever_logging_mod._FALLBACK_LOG

_THROTTLE_REGISTRY = throttle_mod._THROTTLE_REGISTRY
_ThrottleState = throttle_mod._ThrottleState
_normalize_throttle_settings = throttle_mod._normalize_throttle_settings
_deadline_from_settings = throttle_mod._deadline_from_settings
reset_throttle_registry = throttle_mod.reset_throttle_registry

ERR_DEADLINE_EXCEEDED = "retriever_deadline_exceeded"
ERR_INVALID_K = "retriever_invalid_k"
ERR_INVALID_QUERY = "retriever_invalid_query"
ERR_EMBEDDING_FAILED = "retriever_embedding_failed"
ERR_EMBEDDING_INVALID = "retriever_embedding_invalid"
ERR_BUDGET_HIT_PARTIAL = "retriever_budget_hit_partial"
_safe_log = retriever_logging_mod._safe_log
_safe_info = retriever_logging_mod._safe_info
_safe_warning = retriever_logging_mod._safe_warning
_safe_debug = retriever_logging_mod._safe_debug
_apply_error_context = retriever_errors_mod._apply_error_context
_raise_retriever_error = retriever_errors_mod._raise_retriever_error
get_structured_logger = _get_structured_logger


def _throttle_guard(
    key: str,
    settings: Optional[ThrottleSettings],
    *,
    deadline: float | None = None,
) -> Any:
    prev_registry = throttle_mod._THROTTLE_REGISTRY
    if prev_registry is not _THROTTLE_REGISTRY:
        throttle_mod._THROTTLE_REGISTRY = _THROTTLE_REGISTRY
        _safe_debug(
            "retriever.throttle.registry_rebound",
            extra={
                "slug": key,
                "previous": repr(type(prev_registry)),
                "service_only": True,
            },
        )
    return throttle_mod._throttle_guard(key, settings, deadline=deadline)


class ThrottleConfig(TypedDict, total=False):
    candidate_limit: int
    latency_budget_ms: int
    parallelism: int
    sleep_ms_between_calls: int
    acquire_timeout_ms: int


class RetrieverConfig(TypedDict, total=False):
    retriever: ThrottleConfig
    throttle: ThrottleConfig
    candidate_limit: int
    latency_budget_ms: int
    parallelism: int
    sleep_ms_between_calls: int
    acquire_timeout_ms: int


# --------------------------- SSoT per il default limite ---------------------------


def _default_candidate_limit() -> int:
    """Singola fonte di verità del default per candidate_limit (evita drift)."""
    field = QueryParams.__dataclass_fields__.get("candidate_limit")
    if field is None:
        return 4000
    default_val = field.default
    if isinstance(default_val, int):
        return default_val
    if default_val is None or default_val is MISSING:
        return 4000
    try:
        return int(str(default_val))
    except (TypeError, ValueError):
        return 4000


# ----------------------------------- similarità -----------------------------------


def _load_candidates(params: QueryParams) -> tuple[list[dict[str, Any]], float]:
    """Carica tutti i candidati e restituisce (lista, ms)."""
    t0 = time.perf_counter()
    fetched = fetch_candidates(
        params.slug,
        params.scope,
        limit=params.candidate_limit,
        db_path=params.db_path,
    )
    candidates = fetched if isinstance(fetched, list) else list(fetched)
    return candidates, (time.perf_counter() - t0) * 1000.0


# ---------------- Wrapper pubblico per calibrazione candidate_limit -------------


def retrieve_candidates(params: QueryParams) -> list[dict[str, Any]]:
    """Recupera i candidati grezzi per calibrare il `candidate_limit`."""
    validation_mod._validate_params_logged(params)
    if params.candidate_limit == 0:
        return []
    candidates, dt_ms = _load_candidates(params)

    # best-effort: se info fallisce, fallback su debug (entrambi safe)
    extra = {
        "slug": params.slug,
        "scope": params.scope,
        "candidate_limit": int(params.candidate_limit),
        "candidates": int(len(candidates)),
        "ms": float(dt_ms),
    }
    _safe_info("retriever.raw_candidates", extra=extra)
    if not candidates:
        # opzionale: lasciare traccia a debug (non blocca)
        _safe_debug("retriever.raw_candidates.empty", extra=extra)

    return candidates


def _resolve_embedding_model(embeddings_client: EmbeddingsClient, embedding_model: str | None) -> str | None:
    return (
        embedding_model
        or getattr(embeddings_client, "model", None)
        or getattr(embeddings_client, "embedding_model", None)
    )


def _log_query_started(
    params: QueryParams,
    embeddings_client: EmbeddingsClient,
    throttle_cfg: ThrottleSettings | None,
    throttle_key: str,
    response_id: str | None,
    embedding_model: str | None,
) -> None:
    _safe_info(
        "retriever.query.started",
        extra={
            "slug": params.slug,
            "scope": params.scope,
            "response_id": response_id,
            "k": int(params.k),
            "candidate_limit": int(params.candidate_limit),
            "latency_budget_ms": int(throttle_cfg.latency_budget_ms) if throttle_cfg else None,
            "throttle_key": throttle_key,
            "query_len": len(params.query or ""),
            "embedding_model": _resolve_embedding_model(embeddings_client, embedding_model),
        },
    )


def _preflight_soft_fails(
    params: QueryParams,
    *,
    deadline: float | None,
    common_extra: Mapping[str, Any],
    response_id: str | None,
    check_deadline: bool = True,
    check_input: bool = True,
) -> list[SearchResult] | None:
    if check_deadline and throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.throttle.deadline",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "stage": "preflight",
                "response_id": response_id,
            },
        )
        return []

    if check_input and params.k == 0:
        _safe_info("retriever.query.skipped", extra={**common_extra, "reason": "k_is_zero"})
        return []

    if check_input and not params.query.strip():
        _safe_warning("retriever.query.invalid", extra={**common_extra, "reason": "empty_query"})
        return []
    return None


def _embed_query_or_soft_fail(
    params: QueryParams,
    embeddings_client: EmbeddingsClient,
    *,
    deadline: float | None,
    common_extra: Mapping[str, Any],
    response_id: str | None,
    embedding_model: str | None,
) -> tuple[list[float], float] | None:
    if throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.latency_budget.hit",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "stage": "embedding",
                "response_id": response_id,
            },
        )
        return None

    try:
        query_vector, t_emb_ms = embeddings_mod._materialize_query_vector(
            params,
            embeddings_client,
            embedding_model=embedding_model,
        )
    except RetrieverError as exc:
        _apply_error_context(exc, code=ERR_EMBEDDING_FAILED, slug=params.slug, scope=params.scope)
        _safe_warning(
            "retriever.query.embed_failed",
            extra={
                **common_extra,
                "code": ERR_EMBEDDING_FAILED,
                "error": repr(getattr(exc, "__cause__", None) or exc),
            },
        )
        return None

    if query_vector is None:
        _safe_warning(
            "retriever.query.invalid",
            extra={**common_extra, "reason": "empty_embedding", "code": ERR_EMBEDDING_INVALID},
        )
        return None

    _safe_info(
        "retriever.query.embedded",
        extra={
            "slug": params.slug,
            "scope": params.scope,
            "response_id": response_id,
            "ms": float(t_emb_ms),
            "embedding_dims": len(query_vector),
            "embedding_model": _resolve_embedding_model(embeddings_client, embedding_model),
        },
    )

    if throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.latency_budget.hit",
            extra={"slug": params.slug, "scope": params.scope, "stage": "embedding", "response_id": response_id},
        )
        return None
    return query_vector, t_emb_ms


def _fetch_candidates_or_soft_fail(
    params: QueryParams,
    *,
    deadline: float | None,
    common_extra: Mapping[str, Any],
    response_id: str | None,
) -> tuple[list[dict[str, Any]], float] | None:
    if throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.latency_budget.hit",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "stage": "fetch_candidates",
                "response_id": response_id,
            },
        )
        return None

    candidates, t_fetch_ms = _load_candidates(params)
    fetch_budget_hit = throttle_mod._deadline_exceeded(deadline)

    _safe_info(
        "retriever.candidates.fetched",
        extra={
            **common_extra,
            "candidates_loaded": int(len(candidates)),
            "ms": float(t_fetch_ms),
            "budget_hit": bool(fetch_budget_hit),
        },
    )

    if throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.latency_budget.hit",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "stage": "fetch_candidates",
                "response_id": response_id,
            },
        )
        return None
    return candidates, t_fetch_ms


def _rank_or_soft_fail(
    query_vector: list[float],
    candidates: list[dict[str, Any]],
    params: QueryParams,
    *,
    deadline: float | None,
    response_id: str | None,
) -> tuple[list[SearchResult], dict[str, Any]] | None:
    (
        scored_items,
        candidates_count,
        coerce_stats,
        t_score_sort_ms,
        evaluated_count,
        rank_budget_hit,
    ) = _rank_candidates(
        query_vector,
        candidates,
        params.k,
        deadline=deadline,
        abort_if_deadline=True,
    )

    budget_hit = rank_budget_hit
    if budget_hit:
        _safe_warning(
            "retriever.latency_budget.hit",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "stage": "ranking",
                "response_id": response_id,
            },
        )
        return None
    return scored_items, {
        "candidates_count": candidates_count,
        "evaluated_count": evaluated_count,
        "coerce_stats": coerce_stats,
        "t_score_sort_ms": t_score_sort_ms,
        "budget_hit": budget_hit,
    }


def _emit_post_metrics_and_manifest(
    params: QueryParams,
    scored_items: list[SearchResult],
    *,
    response_id: str | None,
    embeddings_client: EmbeddingsClient,
    embedding_model: str | None,
    explain_base_dir: Path | None,
    throttle_cfg: ThrottleSettings | None,
    candidates_count: int,
    evaluated_count: int,
    coerce_stats: Mapping[str, int],
    t_emb_ms: float,
    t_fetch_ms: float,
    t_score_sort_ms: float,
    total_ms: float,
    budget_hit: bool,
) -> None:
    ranking_mod._log_retriever_metrics(
        params=params,
        total_ms=total_ms,
        t_emb_ms=t_emb_ms,
        t_fetch_ms=t_fetch_ms,
        t_score_sort_ms=t_score_sort_ms,
        candidates_count=candidates_count,
        evaluated_count=evaluated_count,
        coerce_stats=coerce_stats,
        response_id=response_id,
    )

    evidence_ids = manifest_mod._build_evidence_ids(scored_items)
    manifest_mod._log_evidence_selected(
        params=params,
        scored_items=scored_items,
        evidence_ids=evidence_ids,
        response_id=response_id,
        budget_hit=budget_hit,
    )
    manifest_mod._write_manifest_if_configured(
        params=params,
        scored_items=scored_items,
        response_id=response_id,
        embeddings_client=embeddings_client,
        embedding_model=embedding_model,
        explain_base_dir=explain_base_dir,
        throttle_cfg=throttle_cfg,
        candidates_count=candidates_count,
        evaluated_count=evaluated_count,
        t_emb_ms=t_emb_ms,
        t_fetch_ms=t_fetch_ms,
        t_score_sort_ms=t_score_sort_ms,
        total_ms=total_ms,
        budget_hit=budget_hit,
        evidence_ids=evidence_ids,
    )

    if throttle_cfg:
        _safe_info(
            "retriever.throttle.metrics",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "throttle": {
                    "latency_budget_ms": int(throttle_cfg.latency_budget_ms),
                    "parallelism": int(throttle_cfg.parallelism),
                    "sleep_ms_between_calls": int(throttle_cfg.sleep_ms_between_calls),
                    "budget_hit": bool(budget_hit),
                    "evaluated": int(evaluated_count),
                },
            },
        )


def search(
    params: QueryParams,
    embeddings_client: EmbeddingsClient,
    *,
    authorizer: Callable[[QueryParams], None] | None = None,
    throttle_check: Callable[[QueryParams], None] | None = None,
    throttle: Optional[ThrottleSettings] = None,
    throttle_key: Optional[str] = None,
    response_id: str | None = None,
    embedding_model: str | None = None,
    explain_base_dir: Path | None = None,
) -> list[SearchResult]:
    """Esegue una ricerca vettoriale sui chunk del workspace indicato."""
    throttle_cfg = throttle_mod._normalize_throttle_settings(throttle)
    deadline = throttle_mod._deadline_from_settings(throttle_cfg)
    throttle_key_eff = throttle_key or params.slug or "retriever"
    try:
        validation_mod._validate_params_logged(params)
    except RetrieverError as exc:
        _apply_error_context(exc, code="retriever_invalid_params", slug=params.slug, scope=params.scope)
        raise

    common_extra = {
        "slug": params.slug,
        "scope": params.scope,
        "candidate_limit": int(params.candidate_limit),
        "response_id": response_id,
    }
    preflight_result = _preflight_soft_fails(
        params,
        deadline=deadline,
        common_extra=common_extra,
        response_id=response_id,
        check_deadline=True,
        check_input=False,
    )
    if preflight_result is not None:
        return preflight_result

    throttle_ctx = _throttle_guard(throttle_key_eff, throttle_cfg, deadline=deadline) if throttle_cfg else nullcontext()

    _log_query_started(
        params,
        embeddings_client,
        throttle_cfg,
        throttle_key_eff,
        response_id,
        embedding_model,
    )

    with throttle_ctx:
        if authorizer is not None:
            authorizer(params)
        if throttle_check is not None:
            throttle_check(params)

        preflight_result = _preflight_soft_fails(
            params,
            deadline=deadline,
            common_extra=common_extra,
            response_id=response_id,
            check_deadline=False,
            check_input=True,
        )
        if preflight_result is not None:
            return preflight_result

        t_total_start = time.perf_counter()

        embed_result = _embed_query_or_soft_fail(
            params,
            embeddings_client,
            deadline=deadline,
            common_extra=common_extra,
            response_id=response_id,
            embedding_model=embedding_model,
        )
        if embed_result is None:
            return []
        query_vector, t_emb_ms = embed_result

        fetch_result = _fetch_candidates_or_soft_fail(
            params,
            deadline=deadline,
            common_extra=common_extra,
            response_id=response_id,
        )
        if fetch_result is None:
            _safe_info("retriever.query.result", extra={**common_extra, "status": "soft_fail", "reason": "fetch"})
            return []
        candidates, t_fetch_ms = fetch_result

        rank_result = _rank_or_soft_fail(
            query_vector,
            candidates,
            params,
            deadline=deadline,
            response_id=response_id,
        )
        if rank_result is None:
            return []
        scored_items, rank_meta = rank_result

        total_ms = (time.perf_counter() - t_total_start) * 1000.0
        _emit_post_metrics_and_manifest(
            params,
            scored_items,
            response_id=response_id,
            embeddings_client=embeddings_client,
            embedding_model=embedding_model,
            explain_base_dir=explain_base_dir,
            throttle_cfg=throttle_cfg,
            candidates_count=int(rank_meta["candidates_count"]),
            evaluated_count=int(rank_meta["evaluated_count"]),
            coerce_stats=rank_meta["coerce_stats"],
            t_emb_ms=float(t_emb_ms),
            t_fetch_ms=float(t_fetch_ms),
            t_score_sort_ms=float(rank_meta["t_score_sort_ms"]),
            total_ms=float(total_ms),
            budget_hit=bool(rank_meta["budget_hit"]),
        )
        return scored_items


def with_config_candidate_limit(
    params: QueryParams,
    config: Optional[Mapping[str, Any] | RetrieverConfig],
) -> QueryParams:
    """Ritorna una copia applicando `candidate_limit` da config se opportuno."""
    default_lim = _default_candidate_limit()

    # Se il caller ha cambiato il limite, non toccare
    if int(params.candidate_limit) != int(default_lim):
        _safe_info("retriever.limit.source", extra={"source": "explicit", "limit": int(params.candidate_limit)})
        return params

    retr = throttle_mod._coerce_retriever_section(config)
    throttle = throttle_mod._coerce_throttle_section(retr)
    cfg_lim_raw = throttle.get("candidate_limit")
    try:
        cfg_lim = int(cfg_lim_raw) if cfg_lim_raw is not None else None
    except Exception:
        cfg_lim = None

    if cfg_lim is not None and cfg_lim > 0:
        safe_lim = max(MIN_CANDIDATE_LIMIT, min(int(cfg_lim), MAX_CANDIDATE_LIMIT))
        _safe_info(
            "retriever.limit.source",
            extra={"source": "config", "limit": int(safe_lim), "limit_requested": int(cfg_lim)},
        )
        return replace(params, candidate_limit=int(safe_lim))

    _safe_info("retriever.limit.source", extra={"source": "default", "limit": int(default_lim)})
    return params


def choose_limit_for_budget(budget_ms: int) -> int:
    """Euristica: mappa il budget di latenza (ms) su candidate_limit."""
    try:
        b = int(budget_ms)
    except Exception:
        b = 0
    if b <= 0:
        return _default_candidate_limit()
    if b <= 180:
        return 1000
    if b <= 280:
        return 2000
    if b <= 420:
        return 4000
    return 8000


def with_config_or_budget(params: QueryParams, config: Optional[Mapping[str, Any]]) -> QueryParams:
    """Applica candidate_limit da config, con supporto auto by budget se abilitato."""
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        _safe_info("retriever.limit.source", extra={"source": "explicit", "limit": int(params.candidate_limit)})
        return params

    retr = throttle_mod._coerce_retriever_section(config)
    auto = bool(retr.get("auto_by_budget", False))
    throttle = throttle_mod._coerce_throttle_section(retr)
    try:
        budget = int(throttle.get("latency_budget_ms", retr.get("latency_budget_ms", 0)) or 0)
    except Exception:
        budget = 0

    if auto and budget > 0:
        chosen = choose_limit_for_budget(budget)
        safe_chosen = max(MIN_CANDIDATE_LIMIT, min(int(chosen), MAX_CANDIDATE_LIMIT))
        if int(safe_chosen) != int(chosen):
            _safe_warning("retriever.limit.clamped", extra={"provided": int(chosen), "effective": int(safe_chosen)})

        _safe_info(
            "retriever.limit.source",
            extra={"source": "auto_by_budget", "budget_ms": int(budget), "limit": int(safe_chosen)},
        )
        return replace(params, candidate_limit=int(safe_chosen))

    try:
        raw = throttle.get("candidate_limit", retr.get("candidate_limit"))
        lim = int(raw) if raw is not None else None
    except Exception:
        lim = None

    if lim and lim > 0:
        safe_lim = max(MIN_CANDIDATE_LIMIT, min(int(lim), MAX_CANDIDATE_LIMIT))
        _safe_info(
            "retriever.limit.source",
            extra={"source": "config", "limit": int(safe_lim), "limit_requested": int(lim)},
        )

        if safe_lim != int(lim):
            _safe_warning("retriever.limit.clamped", extra={"provided": int(lim), "effective": int(safe_lim)})

        return replace(params, candidate_limit=safe_lim)

    _safe_info("retriever.limit.source", extra={"source": "default", "limit": int(default_lim)})
    return params


# ---------------- Facade per wiring reale + preview per la UI ----------------


def search_with_config(
    params: QueryParams,
    config: Optional[Mapping[str, Any]],
    embeddings_client: EmbeddingsClient,
    *,
    authorizer: Callable[[QueryParams], None] | None = None,
    throttle_check: Callable[[QueryParams], None] | None = None,
    response_id: str | None = None,
    embedding_model: str | None = None,
) -> list[SearchResult]:
    """Esegue `with_config_or_budget(...)` e poi `search(...)`."""
    effective = with_config_or_budget(params, config)
    throttle_cfg = throttle_mod._normalize_throttle_settings(throttle_mod._build_throttle_settings(config))
    throttle_key = f"{params.slug}::{params.scope}"
    return search(
        effective,
        embeddings_client,
        authorizer=authorizer,
        throttle_check=throttle_check,
        throttle=throttle_cfg,
        throttle_key=throttle_key,
        response_id=response_id,
        embedding_model=embedding_model,
    )


def preview_effective_candidate_limit(
    params: QueryParams,
    config: Optional[Mapping[str, Any]],
) -> tuple[int, str, int]:
    """Calcola il `candidate_limit` effettivo senza mutare `params` e senza loggare."""
    default_lim = _default_candidate_limit()

    # 1) Esplicito
    if int(params.candidate_limit) != int(default_lim):
        return int(params.candidate_limit), "explicit", 0

    retr = throttle_mod._coerce_retriever_section(config)

    # 2) Auto by budget
    try:
        auto = bool(retr.get("auto_by_budget", False))
        throttle = throttle_mod._coerce_throttle_section(retr)
        budget_ms = int(throttle.get("latency_budget_ms", retr.get("latency_budget_ms", 0)) or 0)
    except Exception:
        auto = False
        budget_ms = 0

    if auto and budget_ms > 0:
        chosen = choose_limit_for_budget(budget_ms)
        safe_chosen = max(MIN_CANDIDATE_LIMIT, min(int(chosen), MAX_CANDIDATE_LIMIT))
        return int(safe_chosen), "auto_by_budget", int(budget_ms)

    # 3) Config
    throttle = throttle_mod._coerce_throttle_section(retr)
    try:
        raw = throttle.get("candidate_limit", retr.get("candidate_limit"))
        lim = int(raw) if raw is not None else None
    except Exception:
        lim = None
    if lim and lim > 0:
        safe_lim = max(MIN_CANDIDATE_LIMIT, min(int(lim), MAX_CANDIDATE_LIMIT))
        return int(safe_lim), "config", 0

    # 4) Default
    return int(default_lim), "default", 0


__all__ = [
    "RetrieverError",  # re-export
    "QueryParams",
    "SearchResult",
    "cosine",
    "retrieve_candidates",
    "search",
    "with_config_candidate_limit",
    "choose_limit_for_budget",
    "with_config_or_budget",
    "search_with_config",
    "preview_effective_candidate_limit",
]
