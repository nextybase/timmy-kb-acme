# SPDX-License-Identifier: GPL-3.0-only
# src/retriever.py
"""Utility di ricerca basata su embedding per la Timmy KB.

Funzioni esposte:
- cosine(a, b) -> float
- retrieve_candidates(params) -> list[dict]
- search(params, embeddings_client) -> list[dict]
- with_config_candidate_limit(params, config) -> params
- choose_limit_for_budget(budget_ms) -> int
- with_config_or_budget(params, config) -> params
- search_with_config(params, config, embeddings_client) -> list[dict]
- preview_effective_candidate_limit(params, config)
  -> (limit:int, source:str, budget_ms:int)

Design:
- Carica fino a `candidate_limit` candidati da SQLite (default: 4000).
- Calcola la similarità coseno in Python sui candidati.
- Restituisce i top-k come dict con: content, meta, score.
"""

from __future__ import annotations

import heapq
import math
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import MISSING, dataclass, replace
from itertools import tee
from pathlib import Path
from typing import Any, Callable, Generator, Iterable, Mapping, Optional, Sequence

from pipeline.embedding_utils import is_numeric_vector, normalize_embeddings
from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient

from .kb_db import fetch_candidates

LOGGER = get_structured_logger("timmy_kb.retriever")


@dataclass(frozen=True)
class QueryParams:
    """Parametri strutturati per la ricerca.

    Note:
    - `db_path`: percorso del DB SQLite; se None, usa il default interno di
      `fetch_candidates`.
    - `project_slug`: progetto/spazio logico da cui recuperare i candidati.
    - `scope`: sotto-spazio o ambito (es. sezione o agente).
    - `query`: testo naturale da embeddare e confrontare con i candidati.
    - `k`: numero di risultati da restituire (top-k).
    - `candidate_limit`: massimo numero di candidati da caricare dal DB.
    """

    db_path: Optional[Path]
    project_slug: str
    scope: str
    query: str
    k: int = 8
    candidate_limit: int = 4000


@dataclass(frozen=True)
class ThrottleSettings:
    latency_budget_ms: int = 0
    parallelism: int = 1
    sleep_ms_between_calls: int = 0


_MAX_PARALLELISM = 32


class _ThrottleState:
    def __init__(self, parallelism: int) -> None:
        self.parallelism = max(1, parallelism)
        self._semaphore = threading.BoundedSemaphore(self.parallelism)
        self._lock = threading.Lock()
        self._last_completed = 0.0

    def acquire(self) -> None:
        self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()

    def wait_interval(self, sleep_ms: int) -> None:
        if sleep_ms <= 0:
            return
        min_interval = sleep_ms / 1000.0
        while True:
            with self._lock:
                last = self._last_completed
            if last == 0.0:
                return
            elapsed = time.perf_counter() - last
            if elapsed >= min_interval:
                return
            time.sleep(min(min_interval - elapsed, 0.05))

    def mark_complete(self) -> None:
        with self._lock:
            self._last_completed = time.perf_counter()


class _ThrottleRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, _ThrottleState] = {}

    def get_state(self, key: str, parallelism: int) -> _ThrottleState:
        normalized = max(1, min(_MAX_PARALLELISM, parallelism))
        with self._lock:
            state = self._states.get(key)
            if state is None or state.parallelism != normalized:
                state = _ThrottleState(normalized)
                self._states[key] = state
        return state


_THROTTLE_REGISTRY = _ThrottleRegistry()


def reset_throttle_registry() -> None:
    """Svuota lo stato di throttling (uso test/benchmark)."""
    with _THROTTLE_REGISTRY._lock:  # pragma: no cover - helper test
        _THROTTLE_REGISTRY._states.clear()


@contextmanager
def _throttle_guard(key: str, settings: Optional[ThrottleSettings]) -> Generator[None, None, None]:
    if settings is None:
        yield
        return
    state = _THROTTLE_REGISTRY.get_state(key, settings.parallelism)
    state.acquire()
    try:
        state.wait_interval(settings.sleep_ms_between_calls)
        yield
    finally:
        state.mark_complete()
        state.release()


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


# --------------------------------- Validazioni ------------------------------------


MIN_CANDIDATE_LIMIT = 500
MAX_CANDIDATE_LIMIT = 20000


def _validate_params(params: QueryParams) -> None:
    """Validazioni minime (fail-fast, senza fallback).

    Range candidato: 500-20000 inclusi.
    """
    if not params.project_slug.strip():
        raise RetrieverError("project_slug vuoto")
    if not params.scope.strip():
        raise RetrieverError("scope vuoto")
    if params.candidate_limit < 0:
        raise RetrieverError("candidate_limit negativo")
    if 0 < params.candidate_limit < MIN_CANDIDATE_LIMIT or params.candidate_limit > MAX_CANDIDATE_LIMIT:
        raise RetrieverError(f"candidate_limit fuori range [{MIN_CANDIDATE_LIMIT}, {MAX_CANDIDATE_LIMIT}]")
    if params.k < 0:
        raise RetrieverError("k negativo")


def _validate_params_logged(params: QueryParams) -> None:
    """Wrapper che logga contesto su validazioni fallite."""
    try:
        _validate_params(params)
    except RetrieverError as exc:
        LOGGER.error(
            "retriever.params.invalid",
            extra={
                "project_slug": params.project_slug,
                "scope": params.scope,
                "candidate_limit": params.candidate_limit,
                "k": params.k,
                "error": str(exc),
            },
        )
        raise


# -------- Helper embedding: short-circuit + validazioni estratte (riduce ciclomatica) --------


def _is_seq_like(x: Any) -> bool:
    return hasattr(x, "__len__") and hasattr(x, "__getitem__") and not isinstance(x, (str, bytes))


def _coerce_candidate_vector(
    raw_vec: Any,
    *,
    idx: int | None = None,
    stats: dict[str, int] | None = None,
) -> list[float] | None:
    """Converte `raw_vec` in `list[float]` applicando:
    - Short-circuit se è già una sequenza numerica piatta (is_numeric_vector)
    - Normalizzazione SSoT altrimenti
    - Controlli di validità su sequenze piatte originali (tutti numerici, finitezza, lunghezza coerente)

    Ritorna:
      - list[float] valida (anche vuota)
      - None se il candidato va skippato (embedding invalido)
    """
    if raw_vec is None:
        # Coerente con la logica precedente: vettore vuoto consente score 0.0
        return []

    # Short-circuit: già list/seq di numerici
    if is_numeric_vector(raw_vec):
        try:
            v = [float(v) for v in raw_vec]
            if stats is not None:
                stats["short"] = stats.get("short", 0) + 1
            return v
        except Exception:
            try:
                LOGGER.debug("skip.candidate.invalid_embedding", extra={"idx": idx})
            except Exception:
                pass
            if stats is not None:
                stats["skipped"] = stats.get("skipped", 0) + 1
            return None

    # Percorso standard: normalizzazione SSoT
    vecs = normalize_embeddings(raw_vec)
    v = vecs[0] if vecs else []
    if not v or (v and not is_numeric_vector(v)):
        try:
            LOGGER.debug("skip.candidate.invalid_embedding", extra={"idx": idx})
        except Exception:
            pass
        if stats is not None:
            stats["skipped"] = stats.get("skipped", 0) + 1
        return None

    # Coerenza per sequenze piatte originali (evita interpretazioni scorrette)
    orig_seq = None
    try:
        if hasattr(raw_vec, "tolist"):
            orig_seq = raw_vec.tolist()
        elif _is_seq_like(raw_vec):
            orig_seq = list(raw_vec)
    except Exception:
        orig_seq = None

    if orig_seq is not None and v:
        # Solo per sequenze piatte 1D (no sotto-sequenze / array 2D)
        try:
            is_flat = True
            for _val in orig_seq:
                if hasattr(_val, "tolist") or _is_seq_like(_val):
                    is_flat = False
                    break
        except Exception:
            is_flat = True

        if is_flat:
            all_numeric = True
            count = 0
            for val in orig_seq:
                try:
                    fv = float(val)
                except Exception:
                    all_numeric = False
                    break
                if not math.isfinite(fv):
                    all_numeric = False
                    break
                count += 1
            if (not all_numeric) or (count != len(v)):
                try:
                    LOGGER.debug("skip.candidate.invalid_embedding_non_numeric", extra={"idx": idx})
                except Exception:
                    pass
                if stats is not None:
                    stats["skipped"] = stats.get("skipped", 0) + 1
                return None

    if stats is not None:
        stats["normalized"] = stats.get("normalized", 0) + 1
    return v


def _materialize_query_vector(
    params: QueryParams,
    embeddings_client: EmbeddingsClient,
) -> tuple[Sequence[float] | None, float]:
    """Calcola l'embedding della query e restituisce (vettore, ms)."""
    t0 = time.time()
    q_raw = embeddings_client.embed_texts([params.query])
    t_ms = (time.time() - t0) * 1000.0
    q_vecs = normalize_embeddings(q_raw)
    if len(q_vecs) == 0 or len(q_vecs[0]) == 0:
        LOGGER.warning(
            "retriever.query.invalid",
            extra={
                "project_slug": params.project_slug,
                "scope": params.scope,
                "reason": "empty_embedding",
            },
        )
        return None, t_ms
    return q_vecs[0], t_ms


def _load_candidates(params: QueryParams) -> tuple[list[dict[str, Any]], float]:
    """Carica tutti i candidati e restituisce (lista, ms)."""
    t0 = time.time()
    candidates = list(
        fetch_candidates(
            params.project_slug,
            params.scope,
            limit=params.candidate_limit,
            db_path=params.db_path,
        )
    )
    return candidates, (time.time() - t0) * 1000.0


def _rank_candidates(
    query_vector: Sequence[float],
    candidates: Sequence[dict[str, Any]],
    k: int,
    *,
    deadline: Optional[float] = None,
) -> tuple[list[dict[str, Any]], int, dict[str, int], float, int, bool]:
    """Restituisce (risultati, n_candidati_tot, stats, ms, valutati, budget_hit)."""
    stats: dict[str, int] = {"short": 0, "normalized": 0, "skipped": 0}
    total_candidates = len(candidates)
    evaluated = 0
    budget_hit = False
    t0 = time.time()
    top_k = max(0, int(k))
    results: list[dict[str, Any]] = []

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
                scored.append((score, idx, {"content": cand["content"], "meta": cand.get("meta", {}), "score": score}))
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
                item = {"content": cand["content"], "meta": cand.get("meta", {}), "score": score}
                key = (score, idx)
                if len(heap) < top_k:
                    heapq.heappush(heap, (key, item))
                else:
                    if key > heap[0][0]:
                        heapq.heapreplace(heap, (key, item))
            results = [item for _, item in sorted(heap, key=lambda t: (-t[0][0], t[0][1]))]

    elapsed_ms = (time.time() - t0) * 1000.0
    return results, total_candidates, stats, elapsed_ms, evaluated, budget_hit


# ---------------- Wrapper pubblico per calibrazione candidate_limit -------------


def retrieve_candidates(params: QueryParams) -> list[dict[str, Any]]:
    """Recupera i candidati grezzi per calibrare il `candidate_limit`.

    Il wrapper applica le validazioni dell'API di ricerca e restituisce i dict
    raw provenienti da `fetch_candidates`, permettendo agli strumenti di
    calibrazione di ispezionare i chunk senza dipendere dal client embedding.
    """
    _validate_params_logged(params)
    if params.candidate_limit == 0:
        return []
    t0 = time.time()
    candidates = list(
        fetch_candidates(
            params.project_slug,
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
                "project_slug": params.project_slug,
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
) -> list[dict[str, Any]]:
    """Esegue la ricerca di chunk rilevanti per una query usando similarità coseno.

    Flusso:
    1) Ottiene l'embedding di `params.query` tramite
       `embeddings_client.embed_texts([str])`.
    2) Carica al massimo `params.candidate_limit` candidati per
       `(project_slug, scope)`.
    3) Calcola similarità coseno e ordina per score decrescente con tie-break
       deterministico.
    4) Restituisce i top-`params.k` in forma di lista di dict:
       {content, meta, score}.

    Note compatibilità embedding:
    - Supporta output `list[list[float]]`, `numpy.ndarray` 2D, `list[np.ndarray]`,
      e vettori singoli (deque/generatori/ndarray/liste).
    - I generatori vengono materializzati; gli array NumPy sono convertiti con `.tolist()`.
    - Distingue batch di vettori da vettore singolo, evitando doppi wrapping.
    - Se batch/vettore è vuoto: warning e `[]`.
    """
    throttle_cfg = _normalize_throttle_settings(throttle)
    throttle_ctx = (
        _throttle_guard(throttle_key or params.project_slug or "retriever", throttle_cfg)
        if throttle_cfg
        else nullcontext()
    )

    with throttle_ctx:
        _validate_params_logged(params)
        if authorizer is not None:
            authorizer(params)
        if throttle_check is not None:
            throttle_check(params)

        # Soft-fail per input non utili
        if params.k == 0:
            return []
        if not params.query.strip():
            LOGGER.warning(
                "retriever.query.invalid",
                extra={
                    "project_slug": params.project_slug,
                    "scope": params.scope,
                    "reason": "empty_query",
                },
            )
            return []
        if params.candidate_limit == 0:
            return []

        deadline = _deadline_from_settings(throttle_cfg)
        budget_hit = False

        t_total_start = time.time()

        # 1) Embedding della query
        query_vector, t_emb_ms = _materialize_query_vector(params, embeddings_client)
        if query_vector is None:
            return []
        if _deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "project_slug": params.project_slug,
                    "scope": params.scope,
                    "stage": "embedding",
                },
            )
            return []

        # 2) Caricamento candidati dal DB
        candidates, t_fetch_ms = _load_candidates(params)
        if _deadline_exceeded(deadline):
            LOGGER.warning(
                "retriever.latency_budget.hit",
                extra={
                    "project_slug": params.project_slug,
                    "scope": params.scope,
                    "stage": "fetch_candidates",
                },
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
        )
        budget_hit = rank_budget_hit
        total_ms = (time.time() - t_total_start) * 1000.0

        # Logging metriche (campi chiave + timing + coerce)
        try:
            LOGGER.info(
                "retriever.metrics",
                extra={
                    "project_slug": params.project_slug,
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

        if throttle_cfg:
            try:
                LOGGER.info(
                    "retriever.throttle.metrics",
                    extra={
                        "project_slug": params.project_slug,
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
                        "project_slug": params.project_slug,
                        "scope": params.scope,
                        "stage": "ranking",
                    },
                )

        return scored_items


def _coerce_retriever_section(config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not config:
        return {}
    retr = config.get("retriever")
    if isinstance(retr, Mapping):
        return retr
    return {}


def _coerce_throttle_section(retriever_section: Mapping[str, Any]) -> Mapping[str, Any]:
    throttle = retriever_section.get("throttle")
    if isinstance(throttle, Mapping):
        return throttle
    legacy: dict[str, Any] = {}
    if "candidate_limit" in retriever_section:
        legacy["candidate_limit"] = retriever_section["candidate_limit"]
    if "latency_budget_ms" in retriever_section:
        legacy["latency_budget_ms"] = retriever_section["latency_budget_ms"]
    if "parallelism" in retriever_section:
        legacy["parallelism"] = retriever_section["parallelism"]
    if "sleep_ms_between_calls" in retriever_section:
        legacy["sleep_ms_between_calls"] = retriever_section["sleep_ms_between_calls"]
    return legacy


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _build_throttle_settings(config: Optional[Mapping[str, Any]]) -> ThrottleSettings:
    retr = _coerce_retriever_section(config)
    throttle = _coerce_throttle_section(retr)
    return ThrottleSettings(
        latency_budget_ms=_safe_int(throttle.get("latency_budget_ms"), _safe_int(retr.get("latency_budget_ms"), 0)),
        parallelism=_safe_int(throttle.get("parallelism"), 1),
        sleep_ms_between_calls=_safe_int(throttle.get("sleep_ms_between_calls"), 0),
    )


def _normalize_throttle_settings(settings: Optional[ThrottleSettings]) -> Optional[ThrottleSettings]:
    if settings is None:
        return None
    normalized = ThrottleSettings(
        latency_budget_ms=max(0, int(settings.latency_budget_ms)),
        parallelism=max(1, min(_MAX_PARALLELISM, int(settings.parallelism))),
        sleep_ms_between_calls=max(0, int(settings.sleep_ms_between_calls)),
    )
    if normalized.latency_budget_ms == 0 and normalized.parallelism == 1 and normalized.sleep_ms_between_calls == 0:
        return None
    return normalized


def _deadline_from_settings(settings: Optional[ThrottleSettings]) -> Optional[float]:
    if settings and settings.latency_budget_ms > 0:
        return time.perf_counter() + settings.latency_budget_ms / 1000.0
    return None


def _deadline_exceeded(deadline: Optional[float]) -> bool:
    return deadline is not None and time.perf_counter() >= deadline


def with_config_candidate_limit(
    params: QueryParams,
    config: Optional[Mapping[str, Any]],
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
    valore diverso dal default per esprimere l’intento.
    """
    default_lim = _default_candidate_limit()

    # Se il caller ha cambiato il limite, non toccare
    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info("limit.source=explicit", extra={"limit": int(params.candidate_limit)})
        except Exception:
            pass
        return params

    retr = _coerce_retriever_section(config)
    throttle = _coerce_throttle_section(retr)
    cfg_lim_raw = throttle.get("candidate_limit")
    try:
        cfg_lim = int(cfg_lim_raw) if cfg_lim_raw is not None else None
    except Exception:
        cfg_lim = None

    if cfg_lim is not None and cfg_lim > 0:
        try:
            LOGGER.info("limit.source=config", extra={"limit": int(cfg_lim)})
        except Exception:
            pass
        return replace(params, candidate_limit=int(cfg_lim))
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
    `src/tools/retriever_calibrate.py` per calibrazione futura.
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

    retr = _coerce_retriever_section(config)
    auto = bool(retr.get("auto_by_budget", False))
    throttle = _coerce_throttle_section(retr)
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
        try:
            LOGGER.info("limit.source=config", extra={"limit": int(lim)})
        except Exception:
            pass
        return replace(params, candidate_limit=int(lim))
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
) -> list[dict[str, Any]]:
    """Esegue `with_config_or_budget(...)` e poi `search(...)`.

    Uso consigliato nei call-site reali per garantire che il limite effettivo
    sia allineato a config/budget e che i log `limit.source=...` vengano emessi.

    Esempio:
        params = QueryParams(db_path=None, project_slug="acme", scope="kb", query=q)
        results = search_with_config(params, cfg, embeddings)
    """
    effective = with_config_or_budget(params, config)
    throttle_cfg = _normalize_throttle_settings(_build_throttle_settings(config))
    throttle_key = f"{params.project_slug}:{params.scope}"
    return search(
        effective,
        embeddings_client,
        authorizer=authorizer,
        throttle_check=throttle_check,
        throttle=throttle_cfg,
        throttle_key=throttle_key,
    )


def preview_effective_candidate_limit(
    params: QueryParams,
    config: Optional[Mapping[str, Any]],
) -> tuple[int, str, int]:
    """Calcola il `candidate_limit` effettivo senza mutare `params` e senza loggare.

    Ritorna (limit, source, budget_ms) dove `source`
    {"explicit", "auto_by_budget", "config", "default"}.
    Utile per la UI per mostrare un’etichetta: "Limite stimato: N".
    """
    default_lim = _default_candidate_limit()

    # 1) Esplicito
    if int(params.candidate_limit) != int(default_lim):
        return int(params.candidate_limit), "explicit", 0

    retr = _coerce_retriever_section(config)
    # 2) Auto by budget
    try:
        auto = bool(retr.get("auto_by_budget", False))
        throttle = _coerce_throttle_section(retr)
        budget_ms = int(throttle.get("latency_budget_ms", retr.get("latency_budget_ms", 0)) or 0)
    except Exception:
        auto = False
        budget_ms = 0
    if auto and budget_ms > 0:
        return choose_limit_for_budget(budget_ms), "auto_by_budget", int(budget_ms)
    # 3) Config
    throttle = _coerce_throttle_section(retr)
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
    "cosine",
    "retrieve_candidates",
    "search",
    "with_config_candidate_limit",
    "choose_limit_for_budget",
    "with_config_or_budget",
    "search_with_config",
    "preview_effective_candidate_limit",
]
