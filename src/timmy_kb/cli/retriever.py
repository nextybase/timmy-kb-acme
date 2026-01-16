# SPDX-License-Identifier: GPL-3.0-only
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

import logging
import time
from contextlib import nullcontext
from dataclasses import MISSING, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypedDict

from kb_db import fetch_candidates
from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient
from timmy_kb.cli import retriever_embeddings as embeddings_mod
from timmy_kb.cli import retriever_manifest as manifest_mod
from timmy_kb.cli import retriever_ranking as ranking_mod
from timmy_kb.cli import retriever_throttle as throttle_mod
from timmy_kb.cli import retriever_validation as validation_mod

LOGGER = get_structured_logger("timmy_kb.retriever")

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


def _log_logging_failure(event: str, exc: Exception, *, extra: Mapping[str, Any] | None = None) -> None:
    payload = {"event": event, "error": repr(exc)}
    if extra:
        payload.update(extra)
    try:
        LOGGER.warning("retriever.log_failed", extra=payload)
    except Exception:
        logging.getLogger("timmy_kb.retriever").warning(
            "retriever.log_failed event=%s error=%r",
            event,
            exc,
        )


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
    """Recupera i candidati grezzi per calibrare il `candidate_limit`.

    Il wrapper applica le validazioni dell'API di ricerca e restituisce i dict
    raw provenienti da `fetch_candidates`, permettendo agli strumenti di
    calibrazione di ispezionare i chunk senza dipendere dal client embedding.
    """
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
    try:
        LOGGER.info(
            "retriever.raw_candidates",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "candidate_limit": int(params.candidate_limit),
                "candidates": int(len(candidates)),
                "ms": float(dt_ms),
            },
        )
    except Exception:
        LOGGER.debug(
            "retrieve_candidates(): loaded %s candidates (limit=%s)",
            len(candidates),
            params.candidate_limit,
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
    """Esegue una ricerca vettoriale sui chunk del workspace indicato.

    Args:
        params: Query strutturata (slug, scope, query, k, candidate_limit).
        embeddings_client: Client compatibile con `EmbeddingsClient`.
        authorizer: Hook opzionale per autorizzare la query.
        throttle_check: Hook opzionale per controlli aggiuntivi di throttling.
        throttle: Configurazione di throttling (rate/deadline).
        throttle_key: Chiave di throttling (default: slug).

    Raises:
        RetrieverError: se i parametri non rispettano i contratti.

    Flusso:
    1) Embedding della query via `embeddings_client.embed_texts([query])`.
    2) Carica fino a `candidate_limit` candidati per `(slug, scope)`.
    3) Similarita' coseno e ordinamento stabile per score decrescente.
    4) Restituisce i top-`k` come lista di `SearchResult`.
    """
    throttle_cfg = throttle_mod._normalize_throttle_settings(throttle)
    deadline = throttle_mod._deadline_from_settings(throttle_cfg)
    try:
        validation_mod._validate_params_logged(params)
    except RetrieverError as exc:
        _apply_error_context(exc, code="retriever_invalid_params", slug=params.slug, scope=params.scope)
        raise
    if throttle_mod._deadline_exceeded(deadline):
        LOGGER.warning(
            "retriever.throttle.deadline",
            extra={"slug": params.slug, "scope": params.scope, "stage": "preflight"},
        )
        _raise_retriever_error(
            "latency budget exceeded",
            code=ERR_DEADLINE_EXCEEDED,
            slug=params.slug,
            scope=params.scope,
            stage="preflight",
        )
    throttle_ctx = (
        _throttle_guard(throttle_key or params.slug or "retriever", throttle_cfg, deadline=deadline)
        if throttle_cfg
        else nullcontext()
    )

    try:
        LOGGER.info(
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
    except Exception:
        pass

    with throttle_ctx:
        if authorizer is not None:
            authorizer(params)
        if throttle_check is not None:
            throttle_check(params)

        # Soft-fail per input non utili
        if params.k == 0:
            try:
                LOGGER.info(
                    "retriever.query.skipped",
                    extra={
                        "slug": params.slug,
                        "scope": params.scope,
                        "reason": "k_is_zero",
                    },
                )
            except Exception as exc:
                LOGGER.warning(
                    "retriever.query.skipped_log_failed",
                    extra={
                        "slug": params.slug,
                        "scope": params.scope,
                        "reason": "k_is_zero",
                        "error": repr(exc),
                    },
                )
            _raise_retriever_error(
                "k is zero",
                code=ERR_INVALID_K,
                slug=params.slug,
                scope=params.scope,
            )
        if not params.query.strip():
            LOGGER.warning(
                "retriever.query.invalid",
                extra={
                    "slug": params.slug,
                    "scope": params.scope,
                    "reason": "empty_query",
                },
            )
            _raise_retriever_error(
                "empty query",
                code=ERR_INVALID_QUERY,
                slug=params.slug,
                scope=params.scope,
            )
        budget_hit = False

        t_total_start = time.time()

        # 1) Embedding della query
        if throttle_mod._deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "slug": params.slug,
                    "scope": params.scope,
                    "stage": "embedding",
                },
            )
            _raise_retriever_error(
                "latency budget exceeded",
                code=ERR_DEADLINE_EXCEEDED,
                slug=params.slug,
                scope=params.scope,
                stage="embedding",
            )
        try:
            query_vector, t_emb_ms = embeddings_mod._materialize_query_vector(
                params,
                embeddings_client,
                embedding_model=embedding_model,
            )
        except RetrieverError as exc:
            _apply_error_context(exc, code=ERR_EMBEDDING_FAILED, slug=params.slug, scope=params.scope)
            raise
        if query_vector is None:
            _raise_retriever_error(
                "invalid embedding",
                code=ERR_EMBEDDING_INVALID,
                slug=params.slug,
                scope=params.scope,
            )
        try:
            LOGGER.info(
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
        except Exception:
            pass
        if throttle_mod._deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "slug": params.slug,
                    "scope": params.scope,
                    "stage": "embedding",
                },
            )
            _raise_retriever_error(
                "latency budget exceeded",
                code=ERR_DEADLINE_EXCEEDED,
                slug=params.slug,
                scope=params.scope,
                stage="embedding",
            )

        # 2) Caricamento candidati dal DB
        if throttle_mod._deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "slug": params.slug,
                    "scope": params.scope,
                    "stage": "fetch_candidates",
                },
            )
            _raise_retriever_error(
                "latency budget exceeded",
                code=ERR_DEADLINE_EXCEEDED,
                slug=params.slug,
                scope=params.scope,
                stage="fetch_candidates",
            )
        candidates, t_fetch_ms = _load_candidates(params)
        fetch_budget_hit = throttle_mod._deadline_exceeded(deadline)
        try:
            LOGGER.info(
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
        except Exception:
            pass
        if throttle_mod._deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "slug": params.slug,
                    "scope": params.scope,
                    "stage": "fetch_candidates",
                },
            )
            _raise_retriever_error(
                "latency budget exceeded",
                code=ERR_DEADLINE_EXCEEDED,
                slug=params.slug,
                scope=params.scope,
                stage="fetch_candidates",
            )

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
            try:
                LOGGER.info(
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
            except Exception:
                pass
            if budget_hit:
                LOGGER.warning(
                    "retriever.latency_budget.hit",
                    extra={
                        "slug": params.slug,
                        "scope": params.scope,
                        "stage": "ranking",
                    },
                )

        if budget_hit:
            _raise_retriever_error(
                "latency budget exceeded during ranking",
                code=ERR_BUDGET_HIT_PARTIAL,
                slug=params.slug,
                scope=params.scope,
                stage="ranking",
                partial_results=scored_items,
            )

        return scored_items


def with_config_candidate_limit(
    params: QueryParams,
    config: Optional[Mapping[str, Any] | RetrieverConfig],
) -> QueryParams:
    """Ritorna una copia applicando `candidate_limit` da config se opportuno.

    Precedenza:
      - Se il chiamante ha personalizzato `params.candidate_limit` (diverso dal
        default del dataclass), NON viene sovrascritto.
      - Se è rimasto al default, e il config contiene `retriever.throttle.candidate_limit`
        valido (>0), viene applicato.

    Nota: se il chiamante imposta esplicitamente il valore uguale al default
    (4000), questa funzione non può distinguerlo dal caso 'non impostato' e
    applicherà il config. In tal caso, evitare questa funzione oppure passare un
    valore diverso dal default per esprimere l'intento.
    """
    default_lim = _default_candidate_limit()

    # Se il caller ha cambiato il limite, non toccare
    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info("limit.source=explicit", extra={"limit": int(params.candidate_limit)})
        except Exception:
            pass
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
        try:
            LOGGER.info(
                "limit.source=config",
                extra={"limit": int(safe_lim), "limit_requested": int(cfg_lim)},
            )
        except Exception:
            pass
        return replace(params, candidate_limit=int(safe_lim))
    try:
        LOGGER.info("limit.source=default", extra={"limit": int(default_lim)})
    except Exception:
        pass
    return params


def choose_limit_for_budget(budget_ms: int) -> int:
    """Euristica: mappa il budget di latenza (ms) su candidate_limit.

    Soglie:
    - <= 180ms  -> 1000
    - <= 280ms  -> 2000
    - <= 420ms  -> 4000
    - >  420ms  -> 8000

    Nota: valori iniziali; verificare su dataset reali. Vedi
    `tools/retriever_calibrate.py` per calibrazione futura.
    """
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
    """Applica candidate_limit da config, con supporto auto by budget se abilitato.

    Precedenza:
      - Parametro esplicito (params.candidate_limit != default) mantiene il valore.
      - Se `retriever.auto_by_budget` è true e `retriever.throttle.latency_budget_ms` > 0 ->
        usa choose_limit_for_budget.
      - Altrimenti, se `retriever.throttle.candidate_limit` > 0 -> usa quello.
      - Fallback: lascia il default del dataclass.
    """
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info("limit.source=explicit", extra={"limit": int(params.candidate_limit)})
        except Exception:
            pass
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
        try:
            LOGGER.info(
                "limit.source=auto_by_budget",
                extra={"budget_ms": int(budget), "limit": int(chosen)},
            )
        except Exception:
            pass
        return replace(params, candidate_limit=chosen)

    try:
        raw = throttle.get("candidate_limit", retr.get("candidate_limit"))
        lim = int(raw) if raw is not None else None
    except Exception:
        lim = None
    if lim and lim > 0:
        safe_lim = max(MIN_CANDIDATE_LIMIT, min(int(lim), MAX_CANDIDATE_LIMIT))
        try:
            LOGGER.info(
                "limit.source=config",
                extra={"limit": int(safe_lim), "limit_requested": int(lim)},
            )
        except Exception as exc:
            _log_logging_failure(
                "limit.source=config",
                exc,
                extra={"limit": int(safe_lim), "limit_requested": int(lim)},
            )
        if safe_lim != int(lim):
            LOGGER.warning(
                "limit.clamped",
                extra={"provided": int(lim), "effective": safe_lim},
            )
        return replace(params, candidate_limit=safe_lim)
    try:
        LOGGER.info("limit.source=default", extra={"limit": int(default_lim)})
    except Exception:
        pass
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
    """Esegue `with_config_or_budget(...)` e poi `search(...)`.

    Uso consigliato nei call-site reali per garantire che il limite effettivo
    sia allineato a config/budget e che i log `limit.source=...` vengano emessi.

    Esempio:
        params = QueryParams(db_path=None, slug="acme", scope="kb", query=q)
        results = search_with_config(params, cfg, embeddings)
    """
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
    """Calcola il `candidate_limit` effettivo senza mutare `params` e senza loggare.

    Ritorna (limit, source, budget_ms) dove `source`
    {"explicit", "auto_by_budget", "config", "default"}.
    Utile per la UI per mostrare un'etichetta: "Limite stimato: N".
    """
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
