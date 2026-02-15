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
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import MISSING, replace
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Optional, TypedDict

from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient
from storage.kb_db import fetch_candidates
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

_LogLevel = Literal["debug", "info", "warning", "error"]


def _emit_log_fallback(event: str, exc: Exception, *, level: _LogLevel, extra: Mapping[str, Any] | None = None) -> None:
    """Fallback deterministico (best-effort) su canale strutturato secondario."""
    payload: dict[str, Any] = {"event": event, "level": level, "log_error": repr(exc)}
    if extra:
        try:
            payload.update(dict(extra))
        except Exception as extra_exc:
            payload["extra_error"] = repr(extra_exc)

    try:
        _FALLBACK_LOG.warning(
            "retriever.log_failed",
            extra={"event": event, "level": level, "payload": payload},
        )
    except Exception:
        return


def _safe_log(event: str, *, level: _LogLevel = "info", extra: Mapping[str, Any] | None = None) -> None:
    """Wrapper unico per loggare senza `try/except/pass` sparsi nel codice."""
    try:
        fn = getattr(LOGGER, level)
        fn(event, extra=dict(extra or {}))
    except Exception as log_exc:
        _emit_log_fallback(event, log_exc, level=level, extra=extra)


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


def _normalize_vector(payload: Any) -> list[float] | None:
    """Assicura che un valore grezzo sia una sequenza di float non vuota."""
    if payload is None:
        return None
    is_sequence = isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray))
    raw_values = list(payload) if is_sequence else [payload]
    if not raw_values:
        return None
    normalized: list[float] = []
    for value in raw_values:
        try:
            normalized.append(float(value))
        except Exception:
            return None
    return normalized or None


def _maybe_tolist(value: Any) -> Any:
    """Converte value.tolist() se disponibile; se fallisce, ritorna value (no silent pass)."""
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            return value
    return value


def _extract_embedding(payload: Any) -> Any:
    """Prende il primo vettore utile da un payload (tipicamente una lista)."""
    payload = _maybe_tolist(payload)

    is_sequence = isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray))
    if is_sequence:
        if not payload:
            return payload
        for element in payload:
            candidate = _maybe_tolist(element)
            if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
                return candidate
        return payload
    return payload


def _is_flat_numeric_sequence(value: Any) -> bool:
    """Verifica se `value` è una sequenza piatta di numeri."""
    if value is None:
        return False
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    length = 0
    for element in value:
        if isinstance(element, Sequence) and not isinstance(element, (str, bytes, bytearray)):
            return False
        try:
            float(element)
        except Exception:
            return False
        length += 1
    return length > 0


def _materialize_query_vector(
    params: QueryParams,
    embeddings_client: EmbeddingsClient,
    *,
    embedding_model: str | None = None,
) -> tuple[list[float] | None, float]:
    """Invoca `embed_texts` e normalizza il primo vettore restituito."""
    t0 = time.time()
    args = ([params.query],)
    kwargs: dict[str, str | None] = {}
    if embedding_model is not None:
        kwargs["model"] = embedding_model

    try:
        payload = embeddings_client.embed_texts(*args, **kwargs)  # type: ignore[call-arg]
    except TypeError as exc:
        if kwargs and "model" in str(exc):
            try:
                payload = embeddings_client.embed_texts(*args)
            except Exception as inner_exc:
                raise RetrieverError("embedding client failure") from inner_exc
        else:
            raise RetrieverError("embedding client failure") from exc
    except Exception as exc:
        raise RetrieverError("embedding client failure") from exc

    elapsed_ms = (time.time() - t0) * 1000.0
    vector = _normalize_vector(_extract_embedding(payload))
    return vector, elapsed_ms


def _coerce_candidate_vector(raw_embedding: Any, *, idx: int, stats: dict[str, int]) -> list[float] | None:
    """Normalizza l'embedding candidato per ranking."""
    if raw_embedding is None:
        return []
    if _is_flat_numeric_sequence(raw_embedding):
        try:
            vector = [float(value) for value in raw_embedding]
        except Exception:
            stats["skipped"] = stats.get("skipped", 0) + 1
            return None
        stats["short"] = stats.get("short", 0) + 1
        return vector

    vector = _normalize_vector(_extract_embedding(raw_embedding))
    if vector is None:
        stats["skipped"] = stats.get("skipped", 0) + 1
        return None
    stats["normalized"] = stats.get("normalized", 0) + 1
    return vector


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


def _budget_hit(deadline: float | None, *, stage: str, slug: str, scope: str) -> bool:
    if not throttle_mod._deadline_exceeded(deadline):
        return False
    _safe_log(
        "retriever.latency_budget.hit",
        level="warning",
        extra={"slug": slug, "scope": scope, "stage": stage},
    )
    return True


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
    _safe_log(
        "retriever.raw_candidates",
        level="info",
        extra={
            "slug": params.slug,
            "scope": params.scope,
            "candidate_limit": int(params.candidate_limit),
            "candidates": int(len(candidates)),
            "ms": float(dt_ms),
        },
    )
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
        _safe_log(
            "retriever.throttle.deadline",
            level="warning",
            extra={"slug": params.slug, "scope": params.scope, "stage": "preflight"},
        )
        return []

    throttle_ctx = (
        _throttle_guard(throttle_key or params.slug or "retriever", throttle_cfg, deadline=deadline)
        if throttle_cfg
        else nullcontext()
    )

    _safe_log(
        "retriever.query.started",
        level="info",
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

        if params.k == 0:
            _safe_log("retriever.query.skipped", level="info", extra={**common_extra, "reason": "k_is_zero"})
            return []

        if not params.query.strip():
            _safe_log("retriever.query.invalid", level="warning", extra={**common_extra, "reason": "empty_query"})
            return []

        t_total_start = time.time()

        if _budget_hit(deadline, stage="pre_embedding", slug=params.slug, scope=params.scope):
            return []

        try:
            query_vector, t_emb_ms = _materialize_query_vector(
                params,
                embeddings_client,
                embedding_model=embedding_model,
            )
        except RetrieverError as exc:
            _apply_error_context(exc, code=ERR_EMBEDDING_FAILED, slug=params.slug, scope=params.scope)
            _safe_log(
                "retriever.query.embed_failed",
                level="warning",
                extra={
                    **common_extra,
                    "code": ERR_EMBEDDING_FAILED,
                    "error": repr(getattr(exc, "__cause__", None) or exc),
                },
            )
            return []

        if query_vector is None:
            _safe_log(
                "retriever.query.embedding_invalid.softfail",
                level="warning",
                extra={**common_extra, "code": ERR_EMBEDDING_INVALID},
            )
            return []

        _safe_log(
            "retriever.query.embedded",
            level="info",
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

        if _budget_hit(deadline, stage="post_embedding", slug=params.slug, scope=params.scope):
            return []

        if _budget_hit(deadline, stage="pre_fetch_candidates", slug=params.slug, scope=params.scope):
            return []

        candidates, t_fetch_ms = _load_candidates(params)
        fetch_budget_hit = throttle_mod._deadline_exceeded(deadline)

        _safe_log(
            "retriever.candidates.fetched",
            level="info",
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

        if _budget_hit(deadline, stage="post_fetch_candidates", slug=params.slug, scope=params.scope):
            return []

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
            _safe_log(
                "retriever.latency_budget.hit",
                level="warning",
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
            _safe_log(
                "retriever.throttle.metrics",
                level="info",
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
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        _safe_log(
            "retriever.limit.source",
            level="info",
            extra={"source": "explicit", "limit": int(params.candidate_limit)},
        )
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
        _safe_log(
            "retriever.limit.source",
            level="info",
            extra={"source": "config", "limit": int(safe_lim), "limit_requested": int(cfg_lim)},
        )
        return replace(params, candidate_limit=int(safe_lim))

    _safe_log("retriever.limit.source", level="info", extra={"source": "default", "limit": int(default_lim)})
    return params


def choose_limit_for_budget(budget_ms: int) -> int:
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
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        _safe_log(
            "retriever.limit.source", level="info", extra={"source": "explicit", "limit": int(params.candidate_limit)}
        )
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
            _safe_log("limit.clamped", level="warning", extra={"provided": int(chosen), "effective": int(safe_chosen)})
        _safe_log(
            "retriever.limit.source",
            level="info",
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
        _safe_log(
            "retriever.limit.source",
            level="info",
            extra={"source": "config", "limit": int(safe_lim), "limit_requested": int(lim)},
        )
        if safe_lim != int(lim):
            _safe_log("limit.clamped", level="warning", extra={"provided": int(lim), "effective": int(safe_lim)})
        return replace(params, candidate_limit=safe_lim)

    _safe_log("retriever.limit.source", level="info", extra={"source": "default", "limit": int(default_lim)})
    return params


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
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        return int(params.candidate_limit), "explicit", 0

    retr = throttle_mod._coerce_retriever_section(config)

    try:
        auto = bool(retr.get("auto_by_budget", False))
        throttle = throttle_mod._coerce_throttle_section(retr)
        budget_ms = int(throttle.get("latency_budget_ms", retr.get("latency_budget_ms", 0)) or 0)
    except Exception:
        auto = False
        budget_ms = 0

    if auto and budget_ms > 0:
        return choose_limit_for_budget(budget_ms), "auto_by_budget", int(budget_ms)

    throttle = throttle_mod._coerce_throttle_section(retr)
    try:
        raw = throttle.get("candidate_limit", retr.get("candidate_limit"))
        lim = int(raw) if raw is not None else None
    except Exception:
        lim = None

    if lim and lim > 0:
        return int(lim), "config", 0

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
