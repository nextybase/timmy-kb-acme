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

import logging
import math
import time
from dataclasses import MISSING, dataclass, replace
from heapq import nlargest
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from pipeline.embedding_utils import is_numeric_vector, normalize_embeddings
from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from semantic.types import EmbeddingsClient

from .kb_db import fetch_candidates

LOGGER = logging.getLogger("timmy_kb.retriever")


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
    """Calcola la similarità coseno tra due vettori numerici.

    Caratteristiche:
    - Iterator-safe: non assume slicing/indicizzazione; non alloca copie.
    - Se una norma è 0 o uno dei due è vuoto, restituisce 0.0.
    - In caso di lunghezze diverse, zip tronca al minimo comune.
    """
    # Stabilizzazione numerica: valuta fattore di scala per evitare overflow
    pairs = [(float(x), float(y)) for x, y in zip(a, b, strict=False)]
    if not pairs:
        return 0.0
    try:
        import sys as _sys

        n = max(1, len(pairs))
        hi = math.sqrt(_sys.float_info.max / float(n)) * 0.99
        lo = math.sqrt(_sys.float_info.min) * 1.01
    except Exception:
        hi = 1.3e154
        lo = 1e-154
    max_abs = 0.0
    for x, y in pairs:
        ax = abs(x)
        ay = abs(y)
        if ax > max_abs:
            max_abs = ax
        if ay > max_abs:
            max_abs = ay
    if max_abs == 0.0:
        return 0.0
    # Se troppo grande -> scala in giù; se troppo piccolo -> scala in su
    if max_abs > hi:
        scale = hi / max_abs
    elif max_abs < lo:
        scale = lo / max_abs
    else:
        scale = 1.0

    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in ((x * scale, y * scale) for x, y in pairs):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0
    s = dot / denom
    # Clamp per errori numerici +/- epsilon
    if s > 1.0:
        return 1.0
    if s < -1.0:
        return -1.0
    return s


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


# -------- Helper embedding: short-circuit + validazioni estratte (riduce ciclomatica) --------


def _is_seq_like(x: Any) -> bool:
    return hasattr(x, "__len__") and hasattr(x, "__getitem__") and not isinstance(x, (str, bytes))


def _coerce_candidate_vector(raw_vec: Any, *, idx: int | None = None) -> list[float] | None:
    """Converte `raw_vec` in `list[float]` applicando:
    - Short-circuit se è già una sequenza numerica piatta (is_numeric_vector)
    - Normalizzazione SSoT altrimenti
    - Controlli di validità su sequenze piatte originali (tutti numerici, finitezza, lunghezza coerente)

    Ritorna:
      - list[float] valida (anche vuota)
      - None se il candidato va skippato (embedding invalido)
    """
    if raw_vec is None:
        return []

    # Short-circuit: già list/seq di numerici
    if is_numeric_vector(raw_vec):
        try:
            return [float(v) for v in raw_vec]  # type: ignore[return-value]
        except Exception:
            try:
                LOGGER.debug("skip.candidate.invalid_embedding", extra={"idx": idx})
            except Exception:
                pass
            return None

    # Percorso standard: normalizzazione SSoT
    vecs = normalize_embeddings(raw_vec)
    v = vecs[0] if vecs else []
    if not v or (v and not is_numeric_vector(v)):
        try:
            LOGGER.debug("skip.candidate.invalid_embedding", extra={"idx": idx})
        except Exception:
            pass
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
                return None

    return v


def _score_candidates(
    qv: Sequence[float],
    cands: Sequence[dict[str, Any]],
) -> Iterable[tuple[dict[str, Any], int]]:
    """Produce coppie (item_dict, idx) con score coseno e indice per tie-break.

    L'item_dict ha le chiavi: content, meta, score (float). Il tie-break deterministico
    usa l'indice di enumerazione (idx ascendente).
    """
    for idx, c in enumerate(cands):
        v = _coerce_candidate_vector(c.get("embedding"), idx=idx)
        if v is None:
            continue
        # v è [] o una lista di float valida
        sim = cosine(qv, v)
        yield (
            {
                "content": c["content"],
                "meta": c.get("meta", {}),
                "score": float(sim),
            },
            idx,
        )


# ---------------- Wrapper pubblico per calibrazione candidate_limit -------------


def retrieve_candidates(params: QueryParams) -> list[dict[str, Any]]:
    """Recupera i candidati grezzi per calibrare il `candidate_limit`.

    Il wrapper applica le validazioni dell'API di ricerca e restituisce i dict
    raw provenienti da `fetch_candidates`, permettendo agli strumenti di
    calibrazione di ispezionare i chunk senza dipendere dal client embedding.
    """
    _validate_params(params)
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


def search(params: QueryParams, embeddings_client: EmbeddingsClient) -> list[dict[str, Any]]:
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
    _validate_params(params)

    # Soft-fail per input non utili
    if params.k == 0:
        return []
    if not params.query.strip():
        LOGGER.warning("query vuota dopo strip; ritorno []")
        return []
    if params.candidate_limit == 0:
        return []

    t0 = time.time()

    # 1) Embedding della query
    t_emb0 = time.time()
    q_raw = embeddings_client.embed_texts([params.query])
    t_emb_ms = (time.time() - t_emb0) * 1000.0

    # Normalizzazione SSoT
    q_vecs = normalize_embeddings(q_raw)
    # Verifiche esplicite di vuoto
    if len(q_vecs) == 0 or len(q_vecs[0]) == 0:
        LOGGER.warning("Empty query embedding; returning no results")
        return []
    qv = q_vecs[0]

    # 2) Caricamento candidati dal DB
    t_fetch0 = time.time()
    cands = list(
        fetch_candidates(
            params.project_slug,
            params.scope,
            limit=params.candidate_limit,
            db_path=params.db_path,
        )
    )
    t_fetch_ms = (time.time() - t_fetch0) * 1000.0
    n = len(cands)

    # 3) Scoring (generator) con indice per tie-break deterministico
    scored_iter = _score_candidates(qv, cands)

    # 4) Ordinamento e top-k con tie-break deterministico (score desc, idx asc)
    k = max(0, int(params.k))
    if k == 0 or n == 0:
        out: list[dict[str, Any]] = []
    else:
        if k >= n:
            # Caso semplice: ordina tutto
            scored_sorted = sorted(scored_iter, key=lambda t: (-t[0]["score"], t[1]))
            out = [item for item, _ in scored_sorted]
        else:
            # O(n log k) mantenendo ordinamento finale deterministico
            topk = nlargest(k, scored_iter, key=lambda t: (t[0]["score"], -t[1]))
            out = [item for item, _ in sorted(topk, key=lambda t: (-t[0]["score"], t[1]))]

    dt = (time.time() - t0) * 1000.0
    t_score_sort_ms = max(0.0, dt - t_emb_ms - t_fetch_ms)

    # Logging metriche (campi chiave + timing)
    try:
        LOGGER.info(
            "retriever.metrics",
            extra={
                "project_slug": params.project_slug,
                "scope": params.scope,
                "k": int(params.k),
                "candidate_limit": int(params.candidate_limit),
                "candidates": int(n),
                "ms": {
                    "total": float(dt),
                    "embed": float(t_emb_ms),
                    "fetch": float(t_fetch_ms),
                    "score_sort": float(t_score_sort_ms),
                },
            },
        )
    except Exception:
        # Fallback di logging compatibile (solo messaggio)
        LOGGER.info(
            ("search(): k=%s candidates=%s limit=%s total=%.1fms embed=%.1fms fetch=%.1fms score+sort=%.1fms"),
            params.k,
            n,
            params.candidate_limit,
            dt,
            t_emb_ms,
            t_fetch_ms,
            t_score_sort_ms,
        )
    return out


def with_config_candidate_limit(
    params: QueryParams,
    config: Optional[dict[str, Any]],
) -> QueryParams:
    """Ritorna una copia applicando `candidate_limit` da config se opportuno.

    Precedenza:
      - Se il chiamante ha personalizzato `params.candidate_limit` (diverso dal
        default del dataclass), NON viene sovrascritto.
      - Se è rimasto al default, e il config contiene `retriever.candidate_limit`
        valido (>0), viene applicato.

    Nota: se il chiamante imposta esplicitamente il valore uguale al default
    (4000), questa funzione non può distinguerlo dal caso “non impostato” e
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

    cfg = config or {}
    try:
        retr = cfg.get("retriever") or {}
        cfg_lim_raw = retr.get("candidate_limit")
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


def with_config_or_budget(params: QueryParams, config: Optional[dict[str, Any]]) -> QueryParams:
    """Applica candidate_limit da config, con supporto auto by budget se abilitato.

    Precedenza:
      - Parametro esplicito (params.candidate_limit != default) mantiene il valore.
      - Se `retriever.auto_by_budget` è true e `latency_budget_ms` > 0 ->
        usa choose_limit_for_budget.
      - Altrimenti, se `retriever.candidate_limit` > 0 -> usa quello.
      - Fallback: lascia il default del dataclass.
    """
    default_lim = _default_candidate_limit()

    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info("limit.source=explicit", extra={"limit": int(params.candidate_limit)})
        except Exception:
            pass
        return params

    cfg = config or {}
    retr = dict(cfg.get("retriever") or {})
    auto = bool(retr.get("auto_by_budget", False))
    budget = 0
    try:
        budget = int(retr.get("latency_budget_ms", 0) or 0)
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
        raw = retr.get("candidate_limit")
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
    config: Optional[dict[str, Any]],
    embeddings_client: EmbeddingsClient,
) -> list[dict[str, Any]]:
    """Esegue `with_config_or_budget(...)` e poi `search(...)`.

    Uso consigliato nei call-site reali per garantire che il limite effettivo
    sia allineato a config/budget e che i log `limit.source=...` vengano emessi.

    Esempio:
        params = QueryParams(db_path=None, project_slug="acme", scope="kb", query=q)
        results = search_with_config(params, cfg, embeddings)
    """
    effective = with_config_or_budget(params, config)
    return search(effective, embeddings_client)


def preview_effective_candidate_limit(
    params: QueryParams,
    config: Optional[dict[str, Any]],
) -> tuple[int, str, int]:
    """Calcola il `candidate_limit` effettivo senza mutare `params` e senza loggare.

    Ritorna (limit, source, budget_ms) dove `source` ∈
    {"explicit", "auto_by_budget", "config", "default"}.
    Utile per la UI per mostrare un’etichetta: "Limite stimato: N".
    """
    default_lim = _default_candidate_limit()

    # 1) Esplicito
    if int(params.candidate_limit) != int(default_lim):
        return int(params.candidate_limit), "explicit", 0

    cfg = config or {}
    retr = dict(cfg.get("retriever") or {})
    # 2) Auto by budget
    try:
        auto = bool(retr.get("auto_by_budget", False))
        budget_ms = int(retr.get("latency_budget_ms", 0) or 0)
    except Exception:
        auto = False
        budget_ms = 0
    if auto and budget_ms > 0:
        return choose_limit_for_budget(budget_ms), "auto_by_budget", int(budget_ms)
    # 3) Config
    try:
        raw = retr.get("candidate_limit")
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
