"""Utility di ricerca basata su embedding per la Timmy KB.

Funzioni esposte:
- cosine(a, b) -> float
- search(params, embeddings_client) -> list[dict]

Design:
- Carica fino a `candidate_limit` candidati da SQLite (default: 4000).
- Calcola la similarità coseno in Python su tutti i candidati.
- Restituisce i top-k come dict con: content, meta, score.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

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


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Calcola la similarità coseno tra due vettori numerici.

    Ritorna 0.0 se uno dei vettori è vuoto o se le norme sono nulle.
    Se le lunghezze differiscono, confronta sul minimo comune.
    """
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        n = min(len(a), len(b))
        a = a[:n]
        b = b[:n]
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def search(params: QueryParams, embeddings_client: EmbeddingsClient) -> List[Dict]:
    """Esegue la ricerca di chunk rilevanti per una query usando similarità coseno.

    Flusso:
    1) Ottiene l'embedding di `params.query` tramite `embeddings_client.embed_texts([str])`.
    2) Carica al massimo `params.candidate_limit` candidati per `(project_slug, scope)`.
    3) Calcola la similarità coseno e ordina i candidati per score decrescente.
    4) Restituisce i top-`params.k` in forma di lista di dict: {content, meta, score}.
    """
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
    LOGGER.debug(
        "Fetched %d candidates for %s/%s",
        len(cands),
        params.project_slug,
        params.scope,
    )

    # 3) Scoring (on-the-fly)
    def _iter_scored():
        for idx, c in enumerate(cands):
            emb = c.get("embedding") or []
            sim = cosine(qv, emb)
            yield (
                {
                    "content": c["content"],
                    "meta": c.get("meta", {}),
                    "score": float(sim),
                },
                idx,
            )

    # 4) Ordinamento e top-k
    k = max(0, int(params.k))
    n = len(cands)
    if k == 0:
        out: List[Dict] = []
    elif k >= n:
        # Comportamento invariato: ordina tutto quando k >= n
        scored_list = [item for item, _ in _iter_scored()]
        scored_list.sort(key=lambda x: x["score"], reverse=True)
        out = scored_list
    else:
        # Selezione efficiente top-k con tie-break deterministico sull'ordine di arrivo
        import heapq

        best = heapq.nlargest(
            k,
            _iter_scored(),
            key=lambda t: (t[0]["score"], -t[1]),  # score desc, idx asc
        )
        out = [it[0] for it in best]

    dt = (time.time() - t0) * 1000.0
    t_score_sort_ms = max(0.0, dt - t_emb_ms - t_fetch_ms)
    try:
        LOGGER.info(
            "search(): k=%s candidates=%s limit=%s total=%.1fms embed=%.1fms fetch=%.1fms score+sort=%.1fms",
            params.k,
            len(cands),
            params.candidate_limit,
            dt,
            t_emb_ms,
            t_fetch_ms,
            t_score_sort_ms,
        )
    except Exception:
        # Fallback logging ultra-compatibile
        LOGGER.info(
            "search(): k=%s candidates=%s took=%.1fms",
            params.k,
            len(cands),
            dt,
        )
    return out


def with_config_candidate_limit(params: QueryParams, config: Optional[Dict]) -> QueryParams:
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
    try:
        default_lim = QueryParams.__dataclass_fields__["candidate_limit"].default  # type: ignore[index]
    except Exception:
        default_lim = 4000

    # Se il caller ha cambiato il limite, non toccare
    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info(
                "limit.source=explicit",
                extra={"limit": int(params.candidate_limit)},
            )
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
        return 4000
    if b <= 180:
        return 1000
    if b <= 280:
        return 2000
    if b <= 420:
        return 4000
    return 8000


def with_config_or_budget(params: QueryParams, config: Optional[Dict]) -> QueryParams:
    """Applica candidate_limit da config, con supporto auto by budget se abilitato.

    Precedenza:
      - Parametro esplicito (params.candidate_limit != default) mantiene il valore.
      - Se `retriever.auto_by_budget` è true e `latency_budget_ms` > 0 -> usa choose_limit_for_budget.
      - Altrimenti, se `retriever.candidate_limit` > 0 -> usa quello.
      - Fallback: lascia il default del dataclass.
    """
    try:
        default_lim = QueryParams.__dataclass_fields__["candidate_limit"].default  # type: ignore[index]
    except Exception:
        default_lim = 4000

    if int(params.candidate_limit) != int(default_lim):
        try:
            LOGGER.info(
                "limit.source=explicit",
                extra={"limit": int(params.candidate_limit)},
            )
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
