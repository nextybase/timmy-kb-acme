# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""
Micro-benchmark per la normalizzazione embeddings in retriever/semantic API.

Esegue misurazioni indicative (best-of-5) su diversi formati di output
di `embed_texts`:
  - numpy.ndarray 2D
  - list[np.ndarray]
  - deque vettore singolo
  - generatore vettore singolo

Uso:
  py -m tools.bench_embeddings_normalization

Nota: benchmark leggero e non scientifico; utile per regression check locale.
"""

import argparse
import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Sequence, Tuple

import numpy as np

import retriever as retr
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import clear_iter_safe_pdfs_cache, ensure_within_and_resolve, iter_safe_pdfs


def _timeit(fn: Callable[[], object], rounds: int = 5) -> float:
    times: list[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def _bench_retriever_normalization() -> Dict[str, Dict[str, float]]:
    """Esegue micro-bench per 3 taglie (S/M/L) e 4 formati di embedding client."""

    def make_stub(n: int):
        def stub_fetch_candidates(slug: str, scope: str, limit: int, db_path: Any) -> Iterable[dict[str, Any]]:
            for _ in range(n):
                yield {"content": "x", "meta": {}, "embedding": [1.0, 0.0]}

        return stub_fetch_candidates

    class Nd2:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Any:
            return np.array([[1.0, 0.0]])

    class ListNd:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> list[Any]:
            return [np.array([1.0, 0.0])]

    class Deq1:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> deque[float]:
            return deque([1.0, 0.0])

    class Gen1:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Iterable[float]:
            def _g() -> Iterable[float]:
                yield 1.0
                yield 0.0

            return _g()

    sizes: Dict[str, int] = {"S": 100, "M": 2000, "L": 8000}
    out: Dict[str, Dict[str, float]] = {}
    for label, n in sizes.items():
        retr.fetch_candidates = make_stub(n)
        params = retr.QueryParams(db_path=None, slug="dummy", scope="kb", query="hello", k=8)
        out[label] = {
            "ndarray_2d": _timeit(lambda: retr.search(params, Nd2())),
            "list_of_ndarray": _timeit(lambda: retr.search(params, ListNd())),
            "deque_vector": _timeit(lambda: retr.search(params, Deq1())),
            "generator_vector": _timeit(lambda: retr.search(params, Gen1())),
        }
    return out


def _prepare_md(book: "Path", n_files: int) -> None:
    book.mkdir(parents=True, exist_ok=True)
    # pulisci esistenti
    for p in book.glob("*.md"):
        try:
            p.unlink()
        except Exception:
            pass
    for i in range(n_files):
        target = ensure_within_and_resolve(book, book / f"F{i:04d}.md")
        safe_write_text(target, f"# File {i}\ncontenuto {i}", encoding="utf-8", atomic=True)


def _prepare_raw_pdfs(raw_dir: "Path", n_files: int) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for p in raw_dir.glob("*.pdf"):
        try:
            p.unlink()
        except Exception:
            pass
    for i in range(n_files):
        pdf_path = ensure_within_and_resolve(raw_dir, raw_dir / f"F{i:04d}.pdf")
        safe_write_text(pdf_path, "%PDF-1.4\n% Timmy KB bench\n", encoding="utf-8", atomic=True)


def _bench_semantic_index() -> Tuple[
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, int]],
    Dict[str, Dict[str, float]],
]:
    import logging
    from dataclasses import dataclass
    from pathlib import Path

    import semantic.api as sapi

    # Stub di _insert_chunks per evitare accesso DB
    sapi._insert_chunks = lambda **kwargs: 1

    @dataclass
    class Ctx:
        base_dir: "Path"
        raw_dir: "Path"
        md_dir: "Path"
        slug: str

    class Nd2:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Any:
            return np.array([[1.0, 0.0] for _ in texts])

    class ListNd:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Any:
            return [np.array([1.0, 0.0]) for _ in texts]

    class GenBatch:
        def embed_texts(self, texts: Sequence[str], *, model: str | None = None) -> Iterable[list[float]]:
            def _gen() -> Iterable[list[float]]:
                for _ in texts:
                    yield [1.0, 0.0]

            return _gen()

    sizes_md: Dict[str, int] = {"S": 2, "M": 50, "L": 200}
    times: Dict[str, Dict[str, float]] = {}
    arts: Dict[str, Dict[str, int]] = {}
    scan_costs: Dict[str, Dict[str, float]] = {}

    for label, n in sizes_md.items():
        slug = f"bench{label}"
        base = Path("output") / f"timmy-kb-{slug}"
        book = base / "book"
        raw_dir = base / "raw"
        base.mkdir(parents=True, exist_ok=True)
        _prepare_md(book, n)
        _prepare_raw_pdfs(raw_dir, n)
        clear_iter_safe_pdfs_cache(root=raw_dir)
        ctx = Ctx(base_dir=base, raw_dir=base / "raw", md_dir=book, slug=slug)
        logger = logging.getLogger(f"bench.semantic.{label}")

        def _run(client: Any) -> int:
            return sapi.index_markdown_to_db(
                ctx,
                logger,
                slug=slug,
                scope="book",
                embeddings_client=client,
                db_path=None,
            )

        t_nd = _timeit(lambda: _run(Nd2()))
        a_nd = _run(Nd2())
        t_ln = _timeit(lambda: _run(ListNd()))
        a_ln = _run(ListNd())
        t_gb = _timeit(lambda: _run(GenBatch()))
        a_gb = _run(GenBatch())

        times[label] = {
            "ndarray_2d": t_nd,
            "list_of_ndarray": t_ln,
            "generator_batch": t_gb,
        }
        arts[label] = {
            "ndarray_2d": a_nd,
            "list_of_ndarray": a_ln,
            "generator_batch": a_gb,
        }
        scan_costs[label] = {
            "cold": _timeit(lambda: sum(1 for _ in iter_safe_pdfs(raw_dir, use_cache=False))),
            "warm_cached": _timeit(lambda: sum(1 for _ in iter_safe_pdfs(raw_dir, use_cache=True))),
        }

    return times, arts, scan_costs


def _compute_delta(cur: Dict[str, Dict[str, float]], base: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for label, cases in cur.items():
        out[label] = {}
        for k, v in cases.items():
            b = base.get(label, {}).get(k)
            if b and b > 0:
                out[label][k] = ((v - b) / b) * 100.0
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark normalizzazione embeddings")
    parser.add_argument("--json", dest="json_path", default=None, help="Percorso file JSON di output")
    parser.add_argument(
        "--baseline",
        dest="baseline_path",
        default=os.environ.get("BENCH_BASELINE_JSON"),
        help="JSON baseline per delta %",
    )
    args = parser.parse_args()

    try:
        results = _bench_retriever_normalization()
        print("Benchmark normalizzazione retriever (s, best-of-5):")
        for sz, items in results.items():
            print(f"  [{sz}]")
            for k, v in items.items():
                print(f"    {k:>18}: {v:.6f}")

        # --------------------------------------------------------------
        # Benchmark normalizzazione in semantic.api.index_markdown_to_db
        # --------------------------------------------------------------
        res_sem_times, res_sem_art, res_scan = _bench_semantic_index()
        print("\nBenchmark normalizzazione semantic.index_markdown_to_db (s, best-of-5):")
        for sz, items in res_sem_times.items():
            print(f"  [{sz}]")
            for k, v in items.items():
                print(f"    {k:>18}: {v:.6f}")
        print("\nCosto iterazione PDF (s, best-of-5):")
        for sz, items in res_scan.items():
            print(f"  [{sz}]")
            for k, v in items.items():
                print(f"    {k:>18}: {v:.6f}")

        # JSON opzionale
        if args.json_path:
            out_dir = os.path.dirname(args.json_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            payload: Dict[str, Any] = {
                "retriever": results,
                "semantic_index_markdown_to_db": res_sem_times,
                "semantic_index_artifacts": res_sem_art,
                "pdf_scan": res_scan,
                "env": {
                    "python": os.environ.get("pythonLocation") or os.environ.get("PYTHON_VERSION"),
                    "github_sha": os.environ.get("GITHUB_SHA"),
                },
                "status": "ok",
            }
            # Delta opzionale
            try:
                base_path = args.baseline_path
                if base_path and os.path.exists(base_path):
                    with open(base_path, "r", encoding="utf-8") as bf:
                        bdata = json.load(bf)
                    b_ret = bdata.get("retriever") or {}
                    b_sem = bdata.get("semantic_index_markdown_to_db") or {}
                    b_scan = bdata.get("pdf_scan") or {}
                    payload["delta_pct"] = {
                        "retriever": _compute_delta(results, b_ret),
                        "semantic_index_markdown_to_db": _compute_delta(res_sem_times, b_sem),
                        "pdf_scan": _compute_delta(res_scan, b_scan),
                    }
            except Exception:
                pass
            json_path = Path(args.json_path)
            safe_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", atomic=True)

        print("OK")
        return 0
    except Exception as e:  # pragma: no cover
        # In caso di errore, non fallire: pubblica JSON con stato error e stampa avviso
        try:
            if args.json_path:
                out_dir = os.path.dirname(args.json_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                json_path = Path(args.json_path)
                safe_write_text(
                    json_path,
                    json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                    atomic=True,
                )
        except Exception:
            pass
        print("âš ï¸Ž regression")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
