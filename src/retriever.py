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
from dataclasses import dataclass
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
    q_vecs = embeddings_client.embed_texts([params.query])
    if not q_vecs or not q_vecs[0]:
        LOGGER.warning("Empty query embedding; returning no results")
        return []
    qv = q_vecs[0]

    # 2) Caricamento candidati dal DB
    cands = list(
        fetch_candidates(
            params.project_slug,
            params.scope,
            limit=params.candidate_limit,
            db_path=params.db_path,
        )
    )
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

    dt = (time.time() - t0) * 1000
    LOGGER.info(
        "search(): k=%s candidates=%s took=%.1fms",
        params.k,
        len(cands),
        dt,
    )
    return out
