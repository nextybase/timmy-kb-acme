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
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient
from storage.kb_db import fetch_candidates
from timmy_kb.cli import retriever_embeddings as embeddings_mod
from timmy_kb.cli import retriever_manifest as manifest_mod
from timmy_kb.cli import retriever_ranking as ranking_mod
from timmy_kb.cli import retriever_throttle as throttle_mod
from timmy_kb.cli import retriever_validation as validation_mod

LOGGER = get_structured_logger("timmy_kb.retriever")
_FALLBACK_LOG = get_structured_logger("timmy_kb.retriever.fallback")

QueryParams = validation_mod.QueryParams
SearchResult = validation_mod.SearchResult
MIN_CANDIDATE_LIMIT = validation_mod.MIN_CANDIDATE_LIMIT
MAX_CANDIDATE_LIMIT = validation_mod.MAX_CANDIDATE_LIMIT
cosine = ranking_mod.cosine
_rank_candidates = ranking_mod._rank_candidates
ThrottleSettings = throttle_mod.ThrottleSettings
_ThrottleState = throttle_mod._ThrottleState
_THROTTLE_REGISTRY = throttle_mod._THROTTLE_REGISTRY
_normalize_throttle_settings = throttle_mod._normalize_throttle_settings
_deadline_from_settings = throttle_mod._deadline_from_settings
reset_throttle_registry = throttle_mod.reset_throttle_registry

ERR_DEADLINE_EXCEEDED = "retriever_deadline_exceeded"
ERR_INVALID_K = "retriever_invalid_k"
ERR_INVALID_QUERY = "retriever_invalid_query"
ERR_EMBEDDING_FAILED = "retriever_embedding_failed"
ERR_EMBEDDING_INVALID = "retriever_embedding_invalid"
ERR_BUDGET_HIT_PARTIAL = "retriever_budget_hit_partial"


# ---------------------------
# Safe logging (no S110: niente try/except/pass)
# ---------------------------


def _safe_info(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    try:
        LOGGER.info(event, extra=dict(extra or {}))
    except Exception:
        _FALLBACK_LOG.info(event, extra={"payload": dict(extra or {})})


def _safe_warning(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    try:
        LOGGER.warning(event, extra=dict(extra or {}))
    except Exception:
        _FALLBACK_LOG.warning(event, extra={"payload": dict(extra or {})})


def _safe_debug(event: str, *, extra: Mapping[str, Any] | None = None) -> None:
    try:
        LOGGER.debug(event, extra=dict(extra or {}))
    except Exception:
        _FALLBACK_LOG.debug(event, extra={"payload": dict(extra or {})})


def _log_logging_failure(event: str, exc: Exception, *, extra: Mapping[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"event": event, "error": repr(exc)}
    if extra:
        payload.update(dict(extra))
    # best-effort e non bloccante
    _safe_warning("retriever.log_failed", extra=payload)


def _apply_error_context(exc: RetrieverError, *, code: str, **extra: Any) -> RetrieverError:
    if getattr(exc, "code", None) is None:
        setattr(exc, "code", code)
    for key, value in extra.items():
        if value is not None and not hasattr(exc, key):
            setattr(exc, key, value)
    return exc


def _raise_retriever_error(message: str, *, code: str, **extra: Any) -> None:
    err = RetrieverError(message)
    _apply_error_context(err, code=code, **extra)
    raise err


def _throttle_guard(key: str, settings: Optional[ThrottleSettings], *, deadline: float | None = None):
    throttle_mod._THROTTLE_REGISTRY = _THROTTLE_REGISTRY
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
    t0 = time.time()
    candidates = list(
        fetch_candidates(
            params.slug,
            params.scope,
            limit=params.candidate_limit,
            db_path=params.db_path,
        )
    )
    return candidates, (time.time() - t0) * 1000.0


# ---------------- Wrapper pubblico per calibrazione candidate_limit -------------


def retrieve_candidates(params: QueryParams) -> list[dict[str, Any]]:
    """Recupera i candidati grezzi per calibrare il `candidate_limit`."""
    validation_mod._validate_params_logged(params)
    if params.candidate_limit == 0:
        return []
    t0 = time.time()
    candidates = list(
        fetch_candidates(
            params.slug,
            params.scope,
            limit=params.candidate_limit,
            db_path=params.db_path,
        )
    )
    dt_ms = (time.time() - t0) * 1000.0

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
    try:
        validation_mod._validate_params_logged(params)
    except RetrieverError as exc:
        _apply_error_context(exc, code="retriever_invalid_params", slug=params.slug, scope=params.scope)
        raise

    if throttle_mod._deadline_exceeded(deadline):
        _safe_warning(
            "retriever.throttle.deadline",
            extra={"slug": params.slug, "scope": params.scope, "stage": "preflight"},
        )
        return []

    throttle_ctx = (
        _throttle_guard(throttle_key or params.slug or "retriever", throttle_cfg, deadline=deadline)
        if throttle_cfg
        else nullcontext()
    )

    _safe_info(
        "retriever.query.started",
        extra={
            "slug": params.slug,
            "scope": params.scope,
            "response_id": response_id,
            "k": int(params.k),
            "candidate_limit": int(params.candidate_limit),
            "latency_budget_ms": int(throttle_cfg.latency_budget_ms) if throttle_cfg else None,
            "throttle_key": throttle_key or params.slug or "retriever",
            "query_len": len(params.query or ""),
        },
    )

    with throttle_ctx:
        if authorizer is not None:
            authorizer(params)
        if throttle_check is not None:
            throttle_check(params)

        common_extra = {
            "slug": params.slug,
            "scope": params.scope,
            "candidate_limit": int(params.candidate_limit),
            "response_id": response_id,
        }

        # Soft-fail per input non utili
        if params.k == 0:
            _safe_info("retriever.query.skipped", extra={**common_extra, "reason": "k_is_zero"})
            return []

        if not params.query.strip():
            _safe_warning("retriever.query.invalid", extra={**common_extra, "reason": "empty_query"})
            return []

        t_total_start = time.time()

        # 1) Embedding della query
        if throttle_mod._deadline_exceeded(deadline):
            _safe_warning(
                "retriever.latency_budget.hit",
                extra={"slug": params.slug, "scope": params.scope, "stage": "embedding"},
            )
            return []

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
            return []

        if query_vector is None:
            _safe_warning(
                "retriever.query.invalid",
                extra={**common_extra, "reason": "empty_embedding", "code": ERR_EMBEDDING_INVALID},
            )
            return []

        _safe_info(
            "retriever.query.embedded",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "response_id": response_id,
                "ms": float(t_emb_ms),
                "embedding_dims": len(query_vector),
                "embedding_model": embedding_model
                or getattr(embeddings_client, "model", None)
                or getattr(embeddings_client, "embedding_model", None),
            },
        )

        if throttle_mod._deadline_exceeded(deadline):
            _safe_warning(
                "retriever.latency_budget.hit",
                extra={"slug": params.slug, "scope": params.scope, "stage": "embedding"},
            )
            return []

        # 2) Caricamento candidati dal DB
        if throttle_mod._deadline_exceeded(deadline):
            _safe_warning(
                "retriever.latency_budget.hit",
                extra={"slug": params.slug, "scope": params.scope, "stage": "fetch_candidates"},
            )
            return []

        candidates, t_fetch_ms = _load_candidates(params)
        fetch_budget_hit = throttle_mod._deadline_exceeded(deadline)

        _safe_info(
            "retriever.candidates.fetched",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "response_id": response_id,
                "candidates_loaded": int(len(candidates)),
                "candidate_limit": int(params.candidate_limit),
                "ms": float(t_fetch_ms),
                "budget_hit": bool(fetch_budget_hit),
            },
        )

        if throttle_mod._deadline_exceeded(deadline):
            _safe_warning(
                "retriever.latency_budget.hit",
                extra={"slug": params.slug, "scope": params.scope, "stage": "fetch_candidates"},
            )
            return []

        # 3) Scoring + ranking deterministico
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

        # Policy: budget hit => evento + soft-fail deterministico
        if budget_hit:
            _safe_warning(
                "retriever.latency_budget.hit",
                extra={"slug": params.slug, "scope": params.scope, "stage": "ranking"},
            )
            return []

        total_ms = (time.time() - t_total_start) * 1000.0
        ranking_mod._log_retriever_metrics(
            params=params,
            total_ms=total_ms,
            t_emb_ms=t_emb_ms,
            t_fetch_ms=t_fetch_ms,
            t_score_sort_ms=t_score_sort_ms,
            candidates_count=candidates_count,
            evaluated_count=evaluated_count,
            coerce_stats=coerce_stats,
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
        try:
            _safe_info(
                "retriever.limit.source",
                extra={"source": "config", "limit": int(safe_lim), "limit_requested": int(lim)},
            )
        except Exception as exc:
            # in realtà _safe_info non dovrebbe mai alzare, ma teniamolo difensivo
            _log_logging_failure(
                "retriever.limit.source",
                exc,
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
        return choose_limit_for_budget(budget_ms), "auto_by_budget", int(budget_ms)

    # 3) Config
    throttle = throttle_mod._coerce_throttle_section(retr)
    try:
        raw = throttle.get("candidate_limit", retr.get("candidate_limit"))
        lim = int(raw) if raw is not None else None
    except Exception:
        lim = None
    if lim and lim > 0:
        return int(lim), "config", 0

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
