from __future__ import annotations

"""
Benchmark locale per il retriever.

Caratteristiche:
- Input: file JSON con array di oggetti query, es. [{"q": "..."}, ...].
  Opzionale ground-truth per hit@k (se presente in ciascun item):
    - "relevant_contains": ["substring1", "substring2", ...]
    - oppure "expected_contains": alias della chiave sopra
- Parametri: --runs N, --k, --candidates "500,1000,...", --slug, --scope, --db, --out.
- Output: stampa una tabella riassuntiva e salva un JSON (default: bench.json).

Nota: nessuna rete; usa un client embedding fittizio.
"""

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List

from src.retriever import QueryParams, search


class _DummyEmbeddings:
    def embed_texts(
        self, texts: Iterable[str], *, model: str | None = None
    ) -> List[List[float]]:  # type: ignore[override]
        out: List[List[float]] = []
        for t in texts:
            # Vettore semplice e deterministico basato su hash locale (nessuna rete)
            h = abs(hash(str(t)))
            # genera 8 valori pseudo-random ma stabili nel run
            vec = [((h >> (i * 8)) & 0xFF) / 255.0 for i in range(8)]
            out.append(vec)
        return out


@dataclass
class BenchRow:
    candidate_limit: int
    p95_ms: float
    mean_ms: float
    hit_at_k: float | None
    runs: int


def _parse_queries(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        # fallback minimale incorporato (ripetibile)
        return [{"q": "onboarding"}, {"q": "drive setup"}, {"q": "semantic tags"}]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Input JSON deve essere una lista di oggetti {q: str, ...}")
    out: list[dict[str, Any]] = []
    for it in data:
        if not isinstance(it, dict) or "q" not in it:
            continue
        out.append({"q": str(it["q"]), **{k: v for k, v in it.items() if k != "q"}})
    return out


def _has_hit(topk: list[dict[str, Any]], truth: list[str]) -> bool:
    txts = [str(x.get("content", "")) for x in topk]
    tt = [s.lower() for s in truth if s]
    for t in tt:
        if any(t in x.lower() for x in txts):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark locale retriever (Timmy KB)")
    ap.add_argument("--queries", type=Path, default=None, help="File JSON con array di {q: str, ...}")
    ap.add_argument("--runs", type=int, default=3, help="Ripetizioni per configurazione")
    ap.add_argument("--k", type=int, default=10, help="Top-k da valutare")
    ap.add_argument(
        "--candidates",
        type=str,
        default="500,1000,2000,5000,10000,20000",
        help="Lista di candidate_limit separati da virgola",
    )
    ap.add_argument("--slug", type=str, default="x", help="project_slug da usare per il DB")
    ap.add_argument("--scope", type=str, default="book", help="scope da usare per il DB")
    ap.add_argument("--db", type=Path, default=None, help="Percorso DB (opzionale)")
    ap.add_argument("--out", type=Path, default=Path("bench.json"), help="File risultati JSON")
    args = ap.parse_args()

    queries = _parse_queries(args.queries)
    candidates_list = [int(x.strip()) for x in str(args.candidates).split(",") if x.strip()]
    emb = _DummyEmbeddings()

    rows: list[BenchRow] = []
    raw_results: dict[str, Any] = {
        "runs": int(args.runs),
        "k": int(args.k),
        "candidates": candidates_list,
        "results": [],
    }

    for cand in candidates_list:
        timings: list[float] = []
        hits: int = 0
        eval_count: int = 0
        for _ in range(int(args.runs)):
            for q in queries:
                params = QueryParams(
                    db_path=args.db,
                    project_slug=args.slug,
                    scope=args.scope,
                    query=str(q["q"]),
                    k=int(args.k),
                    candidate_limit=int(cand),
                )
                t0 = time.perf_counter()
                out = search(params, emb)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                timings.append(dt_ms)

                # hit@k opzionale
                truth = q.get("relevant_contains") or q.get("expected_contains")
                if isinstance(truth, list) and truth:
                    eval_count += 1
                    if _has_hit(out, [str(s) for s in truth]):
                        hits += 1

        p95 = float(statistics.quantiles(timings, n=100)[94]) if timings else 0.0
        mean = float(statistics.fmean(timings)) if timings else 0.0
        hit_ratio = (hits / eval_count) if eval_count > 0 else None
        rows.append(BenchRow(candidate_limit=cand, p95_ms=p95, mean_ms=mean, hit_at_k=hit_ratio, runs=int(args.runs)))
        raw_results["results"].append({
            "candidate_limit": cand,
            "p95_ms": p95,
            "mean_ms": mean,
            "hit_at_k": hit_ratio,
            "samples": len(timings),
        })

    # Stampa tabella compatta
    headers = ["limit", "p95_ms", "mean_ms", "hit@k"]
    print("\nRetriever benchmark (runs={}, k={}, slug={}, scope={})".format(args.runs, args.k, args.slug, args.scope))
    print("{:>8}  {:>10}  {:>10}  {:>8}".format(*headers))
    for r in rows:
        hv = "-" if r.hit_at_k is None else f"{r.hit_at_k:.3f}"
        print(f"{r.candidate_limit:>8d}  {r.p95_ms:>10.1f}  {r.mean_ms:>10.1f}  {hv:>8}")

    # Salva JSON risultati
    try:
        args.out.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSalvato: {args.out}")
    except OSError as e:
        print(f"[warn] salvataggio JSON fallito: {e}")


if __name__ == "__main__":
    main()
