# src/retriever.py
"""Utility di ricerca basata su embedding per la Timmy KB.

Funzioni esposte:
- cosine(a, b) -> float
- search(params, embeddings_client) -> list[dict]
- with_config_candidate_limit(params, config) -> params
- choose_limit_for_budget(budget_ms) -> int
- with_config_or_budget(params, config) -> params
- search_with_config(params, config, embeddings_client) -> list[dict]
- preview_effective_candidate_limit(params, config) -> (limit:int, source:str, budget_ms:int)

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

from pipeline.exceptions import RetrieverError  # modulo comune degli errori
from semantic.types import EmbeddingsClient

from .kb_db import fetch_candidates

LOGGER = logging.getLogger("timmy_kb.retriever")


@dataclass(frozen=True)
class QueryParams:
    """Parametri strutturati per la ricerca.

    Note:
    - `db_path`: percorso del DB SQLite; se None, usa il default interno di `fetch_candidates`.
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
    """Singola fonte di verita del default per candidate_limit (evita drift)."""
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


# ----------------------------------- Similarità -----------------------------------


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    """Calcola la similarità coseno tra due vettori numerici.

    Caratteristiche:
    - Iterator-safe: non assume slicing/indicizzazione; non alloca copie.
    - Se una norma è 0 o uno dei due è vuoto, restituisce 0.0.
    - In caso di lunghezze diverse, zip tronca al minimo comune.
    """
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    return 0.0 if denom == 0.0 else (dot / denom)


# --------------------------------- Validazioni ------------------------------------


MIN_CANDIDATE_LIMIT = 500
MAX_CANDIDATE_LIMIT = 20000


def _validate_params(params: QueryParams) -> None:
    """Validazioni minime (fail-fast, senza fallback). Range candidato: 500-20000 inclusi."""
    if not params.project_slug.strip():
        raise RetrieverError("project_slug vuoto")
    if not params.scope.strip():
        raise RetrieverError("scope vuoto")
    if params.candidate_limit < 0:
        raise RetrieverError("candidate_limit negativo")
    if (
        0 < params.candidate_limit < MIN_CANDIDATE_LIMIT
        or params.candidate_limit > MAX_CANDIDATE_LIMIT
    ):
        raise RetrieverError(
            f"candidate_limit fuori range [{MIN_CANDIDATE_LIMIT}, {MAX_CANDIDATE_LIMIT}]"
        )
    if params.k < 0:
        raise RetrieverError("k negativo")


def _score_candidates(
    qv: Sequence[float],
    cands: Sequence[dict[str, Any]],
) -> Iterable[tuple[dict[str, Any], int]]:
    """Produce coppie (item_dict, idx) con score coseno e indice per tie-break.

    L'item_dict ha le chiavi: content, meta, score (float).
    Il tie-break deterministico usa l'indice di enumerazione (idx ascendente).
    """
    for idx, c in enumerate(cands):
        sim = cosine(qv, c.get("embedding") or [])
        yield (
            {
                "content": c["content"],
                "meta": c.get("meta", {}),
                "score": float(sim),
            },
            idx,
        )


def search(params: QueryParams, embeddings_client: EmbeddingsClient) -> list[dict[str, Any]]:
    """Esegue la ricerca di chunk rilevanti per una query usando similarità coseno.

    Flusso:
    1) Ottiene l'embedding di `params.query` tramite `embeddings_client.embed_texts([str])`.
    2) Carica al massimo `params.candidate_limit` candidati per `(project_slug, scope)`.
    3) Calcola la similarità coseno e ordina i candidati per score decrescente con tie-break deterministico.
    4) Restituisce i top-`params.k` in forma di lista di dict: {content, meta, score}.
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
    q_vecs = embeddings_client.embed_texts([params.query])
    t_emb_ms = (time.time() - t_emb0) * 1000.0
    if not q_vecs or not q_vecs[0]:
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
            # Ottimizzazione O(n log k) mantenendo l'ordinamento finale deterministico
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
            "search(): k=%s candidates=%s limit=%s total=%.1fms embed=%.1fms fetch=%.1fms score+sort=%.1fms",
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
    params: QueryParams, config: Optional[dict[str, Any]]
) -> QueryParams:
    """Ritorna una copia di `params` applicando `candidate_limit` da config se opportuno.

    Precedenza implementata:
      - Se il chiamante ha personalizzato `params.candidate_limit` (diverso dal default del dataclass),
        NON viene sovrascritto.
      - Se è rimasto al default, e il config contiene `retriever.candidate_limit` valido (>0),
        viene applicato.

    Nota: se il chiamante imposta esplicitamente il valore uguale al default (4000), questa funzione
    non può distinguerlo dal caso “non impostato” e applicherà il config. In tal caso, evitare di
    chiamare questa funzione oppure passare un valore diverso dal default per esprimere l’intento.
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

    Soglie (raffinate dopo una prima calibrazione interna):
    - <= 180ms  -> 1000
    - <= 280ms  -> 2000
    - <= 420ms  -> 4000
    - >  420ms  -> 8000

    Nota: questi valori sono un punto di partenza e vanno verificati
    su dataset reali. Usa `src/tools/retriever_calibrate.py` per affinare
    ulteriormente e aggiorna qui le soglie se necessario.
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
      - Se `retriever.auto_by_budget` è true e `latency_budget_ms` > 0 -> usa choose_limit_for_budget.
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
    """Calcola il `candidate_limit` effettivo **senza** mutare `params` e **senza** loggare.

    Ritorna (limit, source, budget_ms) dove `source` ∈ {"explicit","auto_by_budget","config","default"}.
    Utile per la UI per mostrare un'etichetta tipo: "Limite stimato: N".
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
        return choose_limit_for_budget(budget_ms), "auto_by_budget", budget_ms
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
    "RetrieverError",  # re-export dall'omonimo modulo
    "QueryParams",
    "cosine",
    "search",
    "with_config_candidate_limit",
    "choose_limit_for_budget",
    "with_config_or_budget",
    "search_with_config",
    "preview_effective_candidate_limit",
]
