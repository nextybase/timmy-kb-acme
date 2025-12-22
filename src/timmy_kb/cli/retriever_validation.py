# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TypedDict

from pipeline.exceptions import RetrieverError
from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("timmy_kb.retriever")


@dataclass(frozen=True)
class QueryParams:
    """Parametri strutturati per la ricerca.

    Note:
    - `db_path`: percorso del DB SQLite; se None, usa il default interno di
      `fetch_candidates`.
    - `slug`: progetto/spazio logico da cui recuperare i candidati.
    - `scope`: sotto-spazio o ambito (es. sezione o agente).
    - `query`: testo naturale da embeddare e confrontare con i candidati.
    - `k`: numero di risultati da restituire (top-k).
    - `candidate_limit`: massimo numero di candidati da caricare dal DB.
    """

    db_path: Optional[Path]
    slug: str
    scope: str
    query: str
    k: int = 8
    candidate_limit: int = 4000


class SearchMeta(TypedDict, total=False):
    slug: str
    scope: str
    file_path: str
    source: str


class SearchResult(TypedDict):
    content: str
    meta: SearchMeta
    score: float


MIN_CANDIDATE_LIMIT = 500
MAX_CANDIDATE_LIMIT = 20000


def _validate_params(params: QueryParams) -> None:
    """Validazioni minime (fail-fast, senza fallback).

    Range candidato: 500-20000 inclusi.
    """
    if not params.slug.strip():
        raise RetrieverError("slug vuoto")
    if not params.scope.strip():
        raise RetrieverError("scope vuoto")
    if params.candidate_limit <= 0:
        raise RetrieverError("candidate_limit non positivo")
    if params.candidate_limit < MIN_CANDIDATE_LIMIT or params.candidate_limit > MAX_CANDIDATE_LIMIT:
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
                "slug": params.slug,
                "scope": params.scope,
                "candidate_limit": params.candidate_limit,
                "k": params.k,
                "error": str(exc),
            },
        )
        raise
