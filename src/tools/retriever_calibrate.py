"""
Calibrazione retriever: misura la latenza al variare di candidate_limit.

Uso tipico:
  python -m src.tools.retriever_calibrate \
    --project acme --scope Timmy --queries data/queries.txt \
    --limits 1000,2000,4000 --k 8 --repeats 3 [--apply-config] [--json] [--db data/kb.sqlite]

Requisiti (no fallback):
- Client embeddings reale disponibile (es. OpenAIEmbeddings in src.ingest).
- YAML utils e path utils del progetto devono essere importabili.
- Il file delle query è obbligatorio (una query per riga).

Politica:
- Niente fallback/legacy: fail-fast su assenze dipendenze o input non validi.
- Le metriche di fase (embed/fetch/score+sort/total) sono loggate da `src.retriever`.
  Questo script misura e riporta sempre il `total_ms` end-to-end.
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Sequence, Tuple, cast

from src.ingest import OpenAIEmbeddings  # client embeddings reale (no fallback)
from src.kb_db import get_db_path
from src.pipeline.path_utils import ensure_within_and_resolve as _ensure_within, read_text_safe
from src.pipeline.yaml_utils import yaml_read
from src.retriever import QueryParams, search, with_config_or_budget


@dataclass
class Result:
    limit: int
    k: int
    n_cands: int
    total_ms: float
    embed_ms: float | None
    fetch_ms: float | None
    score_sort_ms: float | None


class _EmbeddingsClient:
    """
    Adattatore minimo verso il client embeddings reale.
    Non fa fallback: se il backend non è configurato, fallisce a import-time.
    """

    def __init__(self) -> None:
        self._real = OpenAIEmbeddings()

    def embed_texts(
        self, texts: Sequence[str], *, model: str | None = None
    ) -> Sequence[Sequence[float]]:
        embedded = self._real.embed_texts(texts, model=model)
        return [list(map(float, seq)) for seq in embedded]


def _load_queries(qfile: Path) -> List[str]:
    base = Path(".").resolve()
    qfile = _ensure_within(base, qfile.resolve())
    if not qfile.exists():
        raise SystemExit(f"File queries non trovato: {qfile}")
    content = read_text_safe(base, qfile)
    if not isinstance(content, str):
        raise SystemExit(f"Contenuto non testuale nel file: {qfile}")
    queries = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not queries:
        raise SystemExit(f"Nessuna query valida nel file: {qfile}")
    return queries


def _load_client_config(project_slug: str) -> dict[str, Any]:
    """
    Carica output/timmy-kb-<slug>/config/config.yaml.
    Nessun fallback: solleva se mancante.
    """
    cfg_path = Path("output") / f"timmy-kb-{project_slug}" / "config" / "config.yaml"
    cfg_path = _ensure_within(Path(".").resolve(), cfg_path.resolve())
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config cliente non trovato: {cfg_path}")
    data = yaml_read(cfg_path.parent, cfg_path) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config cliente non valido: {cfg_path}")
    return cast(dict[str, Any], data)


def _apply_policy_with_config(params: QueryParams, project_slug: str) -> QueryParams:
    cfg = _load_client_config(project_slug)
    return with_config_or_budget(params, cfg)


def _run_once(
    project: str,
    scope: str,
    query: str,
    k: int,
    limit: int,
    db_path: Path | None,
    apply_cfg: bool,
) -> Tuple[Result, int]:
    client = _EmbeddingsClient()
    params = QueryParams(
        db_path=db_path, project_slug=project, scope=scope, query=query, k=k, candidate_limit=limit
    )
    if apply_cfg:
        params = _apply_policy_with_config(params, project)

    t0 = time.time()
    out = search(params, client)
    total_ms = (time.time() - t0) * 1000.0

    # n_cands non è esposto: approssimiamo con max(k, len(out))
    n_cands = max(k, len(out))
    return (
        Result(
            limit=limit,
            k=k,
            n_cands=n_cands,
            total_ms=total_ms,
            embed_ms=None,
            fetch_ms=None,
            score_sort_ms=None,
        ),
        len(out),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibrazione retriever per candidate_limit")
    ap.add_argument("--project", required=True, help="Slug progetto")
    ap.add_argument("--scope", required=True, help="Scope (es. agente o sezione)")
    ap.add_argument(
        "--queries",
        required=True,
        help="File con una query per riga (obbligatorio, nessun fallback)",
    )
    ap.add_argument(
        "--limits",
        default="1000,2000,4000",
        help="Lista di limiti candidati, separati da virgola",
    )
    ap.add_argument("--k", type=int, default=8, help="Top-k risultati")
    ap.add_argument("--repeats", type=int, default=3, help="Ripetizioni per media/p95")
    ap.add_argument(
        "--db",
        type=str,
        default=None,
        help="Percorso DB SQLite (default: data/kb.sqlite)",
    )
    ap.add_argument(
        "--dump-top",
        type=str,
        default=None,
        help="Scrive i top-k (primo giro) in JSONL per valutazione qualitativa",
    )
    ap.add_argument(
        "--apply-config",
        action="store_true",
        help=(
            "Applica `with_config_or_budget` usando "
            "output/timmy-kb-<slug>/config/config.yaml (no fallback)"
        ),
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emette un JSON finale con misure per integrazione in CI/plot",
    )
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else get_db_path()
    limits = [int(x) for x in str(args.limits).split(",") if x.strip()]
    queries = _load_queries(Path(args.queries))

    print(
        "DB: {db} | project={proj} scope={scope} k={k} | queries={nq} | "
        "limits={lims} | repeats={rep} | apply_cfg={cfg}".format(
            db=db_path,
            proj=args.project,
            scope=args.scope,
            k=args.k,
            nq=len(queries),
            lims=limits,
            rep=args.repeats,
            cfg=args.apply_config,
        )
    )

    rows: List[Tuple[int, float, float]] = []  # (limit, mean_ms, p95_ms)
    json_rows: list[dict[str, Any]] = []

    for limit in limits:
        samples: List[float] = []
        for rep in range(max(1, int(args.repeats))):
            for q in queries:
                r, _n = _run_once(
                    args.project,
                    args.scope,
                    q,
                    int(args.k),
                    int(limit),
                    db_path,
                    bool(args.apply_config),
                )
                samples.append(r.total_ms)

                if args.dump_top and rep == 0:
                    params = QueryParams(
                        db_path=db_path,
                        project_slug=args.project,
                        scope=args.scope,
                        query=q,
                        k=int(args.k),
                        candidate_limit=int(limit),
                    )
                    if bool(args.apply_config):
                        params = _apply_policy_with_config(params, args.project)
                    client = _EmbeddingsClient()
                    top = search(params, client)
                    rec = {"limit": int(limit), "k": int(args.k), "query": q, "top": top}
                    dump_path = _ensure_within(Path(".").resolve(), Path(args.dump_top).resolve())
                    with dump_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if not samples:
            print(f"limit={limit}: nessun campione")
            continue

        samples.sort()
        mean_ms = stats.fmean(samples)
        idx = max(0, int(round(0.95 * (len(samples) - 1))))  # nearest-rank
        p95_ms = samples[idx]
        rows.append((limit, mean_ms, p95_ms))
        json_rows.append(
            {
                "limit": int(limit),
                "mean_ms": float(f"{mean_ms:.3f}"),
                "p95_ms": float(f"{p95_ms:.3f}"),
                "n": len(samples),
            }
        )
        print(f"limit={limit}: mean={mean_ms:.1f}ms p95={p95_ms:.1f}ms (n={len(samples)})")

    if rows:
        min_p95 = min(p95 for _, _, p95 in rows)
        threshold = min_p95 * 1.10
        candidates = [limit for limit, _, p95 in rows if p95 <= threshold]
        suggested = min(candidates) if candidates else min(limit for limit, *_ in rows)
        print(
            "Suggerimento: candidate_limit={s} "
            "(p95 entro +10% del minimo osservato)".format(s=suggested)
        )
        if args.json:
            payload = {
                "project": args.project,
                "scope": args.scope,
                "k": int(args.k),
                "limits": json_rows,
                "suggested": int(suggested),
            }
            print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
