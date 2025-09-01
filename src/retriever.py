"""Embedding search utilities for Timmy KB.

Functions:
- cosine(a, b) -> float
- search(db_path, embeddings_client, query, project_slug, scope, k) -> list[dict]

Design:
- Fetch a generous LIMIT of candidates from SQLite (e.g., 4000).
- Compute cosine similarity in Python over all candidates.
- Return top-k dicts with content, meta, score.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional

from .kb_db import fetch_candidates

LOGGER = logging.getLogger("timmy_kb.retriever")


def cosine(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 if any vector is empty or norms are zero.
    """
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        # Fallback: compare on min common length
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


def search(
    db_path: Optional[Path],
    embeddings_client,
    query: str,
    project_slug: str,
    scope: str,
    k: int,
    candidate_limit: int = 4000,
) -> List[Dict]:
    """Search relevant chunks for a query using cosine similarity.

    - Embeds the query via `embeddings_client` (must provide `embed_texts([str])`).
    - Loads at most `candidate_limit` candidates for (project_slug, scope).
    - Computes cosine similarity in Python and returns top-k.
    Returns list of dicts: {content, meta, score}.
    """
    t0 = time.time()
    # Embed query
    q_vecs = embeddings_client.embed_texts([query])
    if not q_vecs or not q_vecs[0]:
        LOGGER.warning("Empty query embedding; returning no results")
        return []
    qv = q_vecs[0]

    # Fetch candidates
    cands = list(fetch_candidates(project_slug, scope, limit=candidate_limit, db_path=db_path))
    LOGGER.debug("Fetched %d candidates for %s/%s", len(cands), project_slug, scope)

    # Score
    scored = []
    for c in cands:
        emb = c.get("embedding") or []
        sim = cosine(qv, emb)
        scored.append({"content": c["content"], "meta": c.get("meta", {}), "score": float(sim)})

    # Sort and top-k
    scored.sort(key=lambda x: x["score"], reverse=True)
    out = scored[: max(0, int(k))]

    dt = (time.time() - t0) * 1000
    LOGGER.info("search(): k=%s candidates=%s took=%.1fms", k, len(cands), dt)
    return out
