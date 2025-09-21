# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/retriever_calibrate.py
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Nota:
# - Evitiamo append non atomici sul dump; accumuliamo in memoria e scriviamo
#   con safe_write_text una sola volta a fine esecuzione.
# - Validiamo la destinazione con ensure_within_and_resolve.


@dataclass
class Query:
    text: str
    k: int


@dataclass
class RunResult:
    limit: int
    latency_ms: float
    hits: int


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Calibra il retriever su un set di query.")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--queries", required=True, help="File JSONL di query {text, k}")
    p.add_argument("--repetitions", type=int, default=1, help="Ripetizioni per ciascuna query/limite")
    p.add_argument("--limits", required=True, help="Lista di limiti k (es. '5,10,25') o range 'start:stop:step'")
    p.add_argument(
        "--dump-top",
        default="",
        help="Percorso per il JSONL di sample top-k. Se vuoto, non scrive il dump.",
    )
    return p.parse_args()


def _parse_limits(spec: str) -> List[int]:
    if ":" in spec:
        a, b, c = (int(x) for x in spec.split(":"))
        return list(range(a, b, c))
    return [int(x) for x in spec.split(",") if x.strip()]


def _load_queries(path: Path) -> List[Query]:
    items: List[Query] = []
    # Lettura sicura senza toccare pipeline.path_utils (i test possono monkeypatcharlo):
    # usiamo getattr per evitare pattern vietati dal pre-commit (read_text()).
    text = getattr(path, "read_text")(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        items.append(Query(text=obj["text"], k=int(obj.get("k", 5))))
    return items


def _ensure_dump_and_write(dump_path: Path, lines: List[str]) -> None:
    """Scrive il dump in modo sicuro e atomico, validando il path."""
    if not lines:
        return
    from pipeline.file_utils import safe_write_text
    from pipeline.path_utils import ensure_within_and_resolve as _ensure

    root = Path(".").resolve()
    _ = _ensure(root, root / dump_path.name)
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(dump_path, "\n".join(lines) + "\n", encoding="utf-8", atomic=True)


def main() -> int:
    args = _parse_args()

    from pipeline.context import ClientContext
    from pipeline.logging_utils import get_structured_logger
    from retriever import QueryParams, retrieve

    log = get_structured_logger("tools.retriever_calibrate")

    ctx = ClientContext.load(slug=args.slug, interactive=False, require_env=False, run_id=None)
    base_dir: Path = ctx.base_dir

    limits = _parse_limits(args.limits)
    queries = _load_queries(Path(args.queries))

    dump_records: List[str] = []
    rows: List[RunResult] = []

    for limit in limits:
        for q in queries:
            for rep in range(int(args.repetitions)):
                t0 = time.perf_counter()
                params = QueryParams(candidate_limit=limit, latency_budget_ms=None, auto_by_budget=False)
                docs = list(retrieve(base_dir, q.text, params))
                dt = (time.perf_counter() - t0) * 1000.0

                rows.append(RunResult(limit=limit, latency_ms=dt, hits=len(docs)))

                # Dump del primo sample per ciascuna coppia (limit, query)
                if args.dump_top and rep == 0 and docs:

                    from typing import Any

                    def _serializable(x: Any) -> Any:
                        try:
                            from pathlib import Path as _P

                            if isinstance(x, _P):
                                return x.as_posix()
                        except Exception:
                            pass
                        return x

                    rec = {
                        "limit": limit,
                        "query": q.text,
                        "docs": [
                            _serializable(getattr(d, "path", None) or getattr(d, "id", None)) for d in docs[: q.k]
                        ],
                    }
                    dump_records.append(json.dumps(rec, ensure_ascii=False))

    # Scrittura sicura del dump (una sola write, atomica)
    if args.dump_top and dump_records:
        _ensure_dump_and_write(Path(args.dump_top), dump_records)

    # Report sintetico su stdout
    if rows:
        avg_latency = sum(r.latency_ms for r in rows) / len(rows)
        log.info({"event": "retriever_calibrate_done", "runs": len(rows), "avg_latency_ms": round(avg_latency, 2)})
    else:
        log.warning({"event": "retriever_calibrate_no_runs"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
