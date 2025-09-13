"""
Calibrazione retriever: misura latenza al variare di candidate_limit.

Uso tipico:
  python -m src.tools.retriever_calibrate \
    --project acme --scope Timmy --queries data/queries.txt \
    --limits 1000,2000,4000 --k 8 --repeats 3

Note:
- Nessuna dipendenza nuova. Se `openai` non è installato, si usa un fallback
  che costruisce un embedding di query sintetico con stessa dimensione dei candidati.
- Non cambia alcun default runtime del retriever. Solo benchmark.
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from src.kb_db import fetch_candidates, get_db_path
from src.retriever import QueryParams, search


@dataclass
class Result:
    limit: int
    k: int
    n_cands: int
    total_ms: float
    embed_ms: float | None
    fetch_ms: float | None
    score_sort_ms: float | None


class _FallbackEmbeddings:
    """EmbeddingsClient che evita dipendenze: se openai manca, usa vector sintetico.

    Prova a importare `OpenAIEmbeddings` da `src.ingest`. Se fallisce, ricava la dimensione
    dell'embedding da un candidato e restituisce un vettore unitario.
    """

    def __init__(self, project_slug: str, scope: str, db_path: Path | None) -> None:
        self._real = None
        try:
            from src.ingest import OpenAIEmbeddings  # type: ignore

            self._real = OpenAIEmbeddings()
        except Exception:
            self._real = None
        self._project = project_slug
        self._scope = scope
        self._db_path = db_path

    def _infer_dim(self) -> int:
        for c in fetch_candidates(self._project, self._scope, limit=1, db_path=self._db_path):
            emb = c.get("embedding") or []
            if emb:
                return len(emb)
        # fallback prudente
        return 1536

    def embed_texts(
        self, texts: Sequence[str], *, model: str | None = None
    ) -> Sequence[Sequence[float]]:
        if self._real is not None:
            return self._real.embed_texts(texts, model=model)
        d = self._infer_dim()
        # Vettore unitario sintetico; sufficiente per misurare path di scoring/ordinamento
        return [[1.0] + [0.0] * (max(1, d) - 1) for _ in texts]


def _run_once(
    project: str, scope: str, query: str, k: int, limit: int, db_path: Path | None
) -> Tuple[Result, int]:
    client = _FallbackEmbeddings(project, scope, db_path)
    params = QueryParams(
        db_path=db_path, project_slug=project, scope=scope, query=query, k=k, candidate_limit=limit
    )

    t0 = time.time()
    out = search(params, client)
    total_ms = (time.time() - t0) * 1000.0

    # Deduce n_cands dall'output (non esposto): approssimiamo con max(k, len(out))
    n_cands = max(k, len(out))

    # Notiamo che retriever.logga le fasi: qui manteniamo solo total_ms per robustezza
    return Result(
        limit=limit,
        k=k,
        n_cands=n_cands,
        total_ms=total_ms,
        embed_ms=None,
        fetch_ms=None,
        score_sort_ms=None,
    ), len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibrazione retriever per candidate_limit")
    ap.add_argument("--project", required=True, help="Slug progetto")
    ap.add_argument("--scope", required=True, help="Scope (es. agente o sezione)")
    ap.add_argument("--queries", required=False, help="File con una query per riga")
    ap.add_argument(
        "--limits", default="1000,2000,4000", help="Lista di limiti candidati, separati da virgola"
    )
    ap.add_argument("--k", type=int, default=8, help="Top-k risultati")
    ap.add_argument("--repeats", type=int, default=3, help="Ripetizioni per media/p95")
    ap.add_argument(
        "--db", type=str, default=None, help="Percorso DB SQLite (default: data/kb.sqlite)"
    )
    ap.add_argument(
        "--dump-top",
        type=str,
        default=None,
        help="Scrive i top-k (primo giro) in JSONL per valutazione qualitativa",
    )
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else get_db_path()
    limits = [int(x) for x in str(args.limits).split(",") if x.strip()]

    queries: List[str]
    if args.queries:
        qf = Path(args.queries)
        if not qf.exists():
            raise SystemExit(f"File queries non trovato: {qf}")
        queries = [ln.strip() for ln in qf.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        # fallback minimale: una query neutra; suggerito fornire un file reale
        queries = ["documentation system setup", "how to configure project", "export procedure"]

    print(f"DB: {db_path} | project={args.project} scope={args.scope} k={args.k}")
    print(f"Queries: {len(queries)} | Limits: {limits} | Repeats: {args.repeats}")

    # Misura per ciascun limit
    rows: List[Tuple[int, float, float]] = []  # (limit, mean_ms, p95_ms)
    for limit in limits:
        samples: List[float] = []
        for _ in range(max(1, int(args.repeats))):
            for q in queries:
                r, n = _run_once(args.project, args.scope, q, int(args.k), int(limit), db_path)
                samples.append(r.total_ms)
                # Dump qualitativo solo al primo giro per non gonfiare l'output
                if args.dump_top and _ == 0:
                    try:
                        params = QueryParams(
                            db_path=db_path,
                            project_slug=args.project,
                            scope=args.scope,
                            query=q,
                            k=int(args.k),
                            candidate_limit=int(limit),
                        )
                        client = _FallbackEmbeddings(args.project, args.scope, db_path)
                        top = search(params, client)
                        rec = {"limit": int(limit), "k": int(args.k), "query": q, "top": top}
                        with open(args.dump_top, "a", encoding="utf-8") as f:
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    except Exception:
                        pass
        if not samples:
            print(f"limit={limit}: nessun campione")
            continue
        samples.sort()
        mean_ms = stats.fmean(samples)
        p95_ms = samples[max(0, int(round(0.95 * (len(samples) - 1))))]
        rows.append((limit, mean_ms, p95_ms))
        print(f"limit={limit}: mean={mean_ms:.1f}ms p95={p95_ms:.1f}ms (n={len(samples)})")

    # Suggerimento euristico: scegliere il minimo limit che rispetta il miglior tradeoff
    if rows:
        # Preferisci il più piccolo limit con p95 entro +10% del minimo p95 osservato
        min_p95 = min(p95 for _, _, p95 in rows)
        threshold = min_p95 * 1.10
        candidates = [limit for limit, _, p95 in rows if p95 <= threshold]
        suggested = min(candidates) if candidates else min(limit for limit, *_ in rows)
        print(f"Suggerimento: candidate_limit={suggested} (p95 entro +10% del minimo osservato)")


if __name__ == "__main__":
    main()
