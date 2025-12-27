# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/retriever_calibrate.py
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.path_utils import ensure_within_and_resolve
from storage.kb_store import KbStore


@dataclass
class Query:
    text: str
    k: int


@dataclass
class RunResult:
    limit: int
    latency_ms: float
    hits: int


DEF_SCOPE = "book"


def _parse_args() -> argparse.Namespace:
    """Parsa gli argomenti CLI per la calibrazione del retriever."""
    parser = argparse.ArgumentParser(description="Calibra il retriever su un set di query.")
    parser.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    parser.add_argument("--scope", default=DEF_SCOPE, help="Scope semantico (es. book, faq).")
    parser.add_argument("--queries", required=True, help="File JSONL di query {text, k}")
    parser.add_argument("--repetitions", type=int, default=1, help="Ripetizioni per ciascuna query/limite")
    parser.add_argument(
        "--limits",
        required=True,
        help="Lista di limiti (es. '500,1000,2000') o range 'start:stop:step'",
    )
    parser.add_argument(
        "--dump-top",
        default="",
        help="Percorso per il JSONL di sample top-k (vuoto = nessun dump)",
    )
    return parser.parse_args()


def _parse_limits(spec: str) -> list[int]:
    if ":" in spec:
        start, stop, step = (int(x) for x in spec.split(":"))
        return list(range(start, stop, step))
    return [int(x) for x in spec.split(",") if x.strip()]


def _load_queries(base_dir: Path, path: Path) -> list[Query]:
    items: list[Query] = []
    from pipeline.path_utils import read_text_safe

    if path.is_absolute():
        root = path.parent.resolve()
        candidate = path
    else:
        root = base_dir.resolve()
        candidate = root / path
    text = read_text_safe(root, candidate)
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        items.append(Query(text=str(obj["text"]), k=int(obj.get("k", 5))))
    return items


def _ensure_dump_and_write(dump_path: Path, lines: list[str]) -> None:
    """Scrive il dump in modo sicuro e atomico, validando il percorso."""
    if not lines:
        return
    from pipeline.file_utils import safe_write_text
    from pipeline.path_utils import ensure_within_and_resolve

    root = Path(".").resolve()
    candidate = dump_path.resolve(strict=False)
    safe_path = ensure_within_and_resolve(root, candidate)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(
        safe_path,
        "\n".join(lines) + "\n",
        encoding="utf-8",
        atomic=True,
    )


def _extract_dump_docs(candidates: list[dict[str, Any]], top_k: int) -> list[str | None]:
    docs: list[str | None] = []
    for cand in candidates[:top_k]:
        identifier: str | None = None
        if isinstance(cand, dict):
            meta = cand.get("meta")
            if isinstance(meta, dict):
                for key in ("path", "document_path", "source_path", "id", "slug"):
                    value = meta.get(key)
                    if isinstance(value, str) and value.strip():
                        identifier = value
                        break
        docs.append(identifier)
    return docs


def run_single_calibration(
    *,
    slug: str,
    scope: str,
    store: KbStore,
    limit: int,
    query_index: int,
    query: Query,
    repetitions: int,
    dump_top_path: str,
    log,
    retrieve_candidates,
    RetrieverError,
    QueryParams,
) -> tuple[list[RunResult], list[str]]:
    """
    Esegue la calibrazione per una singola coppia (limit, query) ripetuta `repetitions` volte.

    Ritorna:
      - una lista di RunResult (uno per ripetizione riuscita),
      - una lista di righe JSON (stringhe) da aggiungere al dump top-k (0 o 1 record).
    """
    rows: list[RunResult] = []
    dump_records: list[str] = []
    for repetition in range(repetitions):
        db_path = store.effective_db_path()
        params = QueryParams(
            db_path=db_path,
            slug=slug,
            scope=scope,
            query=query.text,
            k=query.k,
            candidate_limit=limit,
        )
        t0 = time.perf_counter()
        try:
            candidates = retrieve_candidates(params)
        except RetrieverError as exc:  # type: ignore[misc]
            log.error(
                "retriever_calibrate.retrieve_failed",
                extra={
                    "slug": slug,
                    "scope": scope,
                    "limit": limit,
                    "query_index": query_index,
                    "error": str(exc),
                },
            )
            continue
        dt_ms = (time.perf_counter() - t0) * 1000.0

        rows.append(RunResult(limit=limit, latency_ms=dt_ms, hits=len(candidates)))

        log.info(
            "retriever_calibrate.run",
            extra={
                "slug": slug,
                "scope": scope,
                "limit": limit,
                "query_index": query_index,
                "repetition": repetition,
                "hits": len(candidates),
                "latency_ms": round(dt_ms, 3),
            },
        )

        if dump_top_path and repetition == 0 and candidates:
            record = {
                "limit": limit,
                "query": query.text,
                "docs": _extract_dump_docs(candidates, query.k),
            }
            dump_records.append(json.dumps(record, ensure_ascii=False))
    return rows, dump_records


def aggregate_results(
    *,
    slug: str,
    scope: str,
    rows: list[RunResult],
    log,
) -> None:
    """
    Logga il riepilogo finale della calibrazione.

    Se ci sono run registrati, logga retriever_calibrate.done con avg_latency_ms e runs;
    altrimenti logga retriever_calibrate.no_runs.
    """
    if rows:
        avg_latency = sum(r.latency_ms for r in rows) / len(rows)
        log.info(
            "retriever_calibrate.done",
            extra={
                "slug": slug,
                "scope": scope,
                "runs": len(rows),
                "avg_latency_ms": round(avg_latency, 2),
            },
        )
    else:
        log.warning(
            "retriever_calibrate.no_runs",
            extra={"slug": slug, "scope": scope},
        )


def main() -> int:
    args = _parse_args()

    from pipeline.context import ClientContext
    from pipeline.logging_utils import get_structured_logger
    from timmy_kb.cli.retriever import QueryParams, RetrieverError, retrieve_candidates

    log = get_structured_logger("tools.retriever_calibrate")

    ctx = ClientContext.load(slug=args.slug, interactive=False, require_env=False, run_id=None)
    slug = ctx.slug
    base_attr = getattr(ctx, "base_dir", None)
    if base_attr is not None:
        workspace = Path(base_attr).resolve()
    else:
        root = Path(OUTPUT_DIR_NAME)
        candidate = root / f"{REPO_NAME_PREFIX}{slug}"
        workspace = ensure_within_and_resolve(root, candidate)
    store = KbStore.for_slug(slug=slug, base_dir=workspace)
    scope = str(args.scope or DEF_SCOPE).strip() or DEF_SCOPE
    base_dir = Path(".").resolve()

    limits = _parse_limits(args.limits)
    queries = _load_queries(base_dir, Path(args.queries))

    if not limits:
        log.warning("retriever_calibrate.no_limits", extra={"slug": slug, "scope": scope})
        return 0
    if not queries:
        log.warning("retriever_calibrate.no_queries", extra={"slug": slug, "scope": scope})
        return 0

    log.info(
        "retriever_calibrate.start",
        extra={
            "slug": slug,
            "scope": scope,
            "limits": limits,
            "queries": len(queries),
            "repetitions": int(args.repetitions),
        },
    )

    dump_records: list[str] = []
    rows: list[RunResult] = []
    repetitions = int(args.repetitions)
    dump_top_path = str(args.dump_top or "")

    for limit in limits:
        for query_index, query in enumerate(queries):
            run_rows, run_dump = run_single_calibration(
                slug=slug,
                scope=scope,
                store=store,
                limit=limit,
                query_index=query_index,
                query=query,
                repetitions=repetitions,
                dump_top_path=dump_top_path,
                log=log,
                retrieve_candidates=retrieve_candidates,
                RetrieverError=RetrieverError,
                QueryParams=QueryParams,
            )
            rows.extend(run_rows)
            dump_records.extend(run_dump)

    if args.dump_top and dump_records:
        _ensure_dump_and_write(Path(args.dump_top), dump_records)

    aggregate_results(
        slug=slug,
        scope=scope,
        rows=rows,
        log=log,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Nota: genera prima il dummy ("py src/tools/gen_dummy_kb.py --slug dummy"), poi esegui
# "py src/tools/retriever_calibrate.py --slug dummy --scope book" e aggiungi
# "--queries tests/data/retriever_queries.jsonl --limits 500:3000:500" come da docs/test_suite.md.
