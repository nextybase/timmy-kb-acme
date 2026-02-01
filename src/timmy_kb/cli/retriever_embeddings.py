# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import math
import time
from typing import Any, Sequence

from pipeline.embedding_utils import is_numeric_vector, normalize_embeddings
from pipeline.exceptions import RetrieverError
from pipeline.logging_utils import get_structured_logger
from semantic.types import EmbeddingsClient
from timmy_kb.cli import retriever_validation as validation_mod

LOGGER = get_structured_logger("timmy_kb.retriever")

QueryParams = validation_mod.QueryParams


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
    *,
    embedding_model: str | None = None,
) -> tuple[Sequence[float] | None, float]:
    """Calcola l'embedding della query e restituisce (vettore, ms)."""
    t0 = time.time()
    try:
        if embedding_model:
            q_raw = embeddings_client.embed_texts([params.query], model=embedding_model)
        else:
            q_raw = embeddings_client.embed_texts([params.query])
    except Exception as exc:
        t_ms = (time.time() - t0) * 1000.0
        LOGGER.warning(
            "retriever.query.embed_failed",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "error": repr(exc),
                "ms": float(t_ms),
            },
        )
        raise RetrieverError("embedding fallita") from exc
    t_ms = (time.time() - t0) * 1000.0
    q_vecs = normalize_embeddings(q_raw)
    if len(q_vecs) == 0 or len(q_vecs[0]) == 0:
        LOGGER.warning(
            "retriever.query.invalid",
            extra={
                "slug": params.slug,
                "scope": params.scope,
                "reason": "empty_embedding",
            },
        )
        return None, t_ms
    return q_vecs[0], t_ms
