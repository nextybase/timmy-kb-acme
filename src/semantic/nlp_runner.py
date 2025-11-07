# SPDX-License-Identifier: GPL-3.0-or-later
"""Runner dedicato alle fasi NLP (doc_terms + clustering) della pipeline tag onboarding."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, cast

import storage.tags_store as tags_store
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from storage.tags_store import clear_doc_terms, list_documents, upsert_folder_term, upsert_term

__all__ = [
    "DocTask",
    "FolderCache",
    "collect_doc_tasks",
    "process_document",
    "persist_sections",
    "run_doc_terms_pipeline",
]


@dataclass(frozen=True)
class DocTask:
    doc_id: int
    pdf_path: Path


@dataclass(frozen=True)
class FolderCache:
    paths_by_id: dict[int, Path]
    doc_ids_by_folder: dict[Optional[int], list[int]]


def collect_doc_tasks(
    conn: Any,
    *,
    raw_dir_path: Path,
    only_missing: bool,
    rebuild: bool,
    logger: Optional[logging.Logger] = None,
) -> tuple[list[DocTask], int, FolderCache]:
    """Costruisce la lista di documenti da processare e la cache delle cartelle."""
    log = logger or get_structured_logger("semantic.nlp.collect")
    docs = list_documents(conn)
    tasks: list[DocTask] = []
    paths_by_id: dict[int, Path] = {}
    doc_ids_by_folder: defaultdict[Optional[int], list[int]] = defaultdict(list)

    doc_terms_index: set[int] = set()
    if only_missing or rebuild:
        doc_terms_index = {
            int(row[0])
            for row in conn.execute("SELECT DISTINCT document_id FROM doc_terms").fetchall()
            if row[0] is not None
        }

    for row in conn.execute("SELECT id, path FROM folders ORDER BY id ASC").fetchall():
        try:
            folder_id = int(row[0])
        except (TypeError, ValueError):
            continue
        folder_path_str = row[1]
        folder_path = Path(str(folder_path_str)) if folder_path_str else Path("raw")
        paths_by_id[folder_id] = folder_path

    def _abs_path_for(doc: dict[str, Any]) -> Optional[Path]:
        folder_id_val = doc.get("folder_id")
        try:
            folder_id = int(folder_id_val) if folder_id_val is not None else None
        except (TypeError, ValueError):
            folder_id = None

        folder_db_path = Path("raw")
        if folder_id is not None:
            folder_db_path = paths_by_id.get(folder_id, Path("raw"))

        parts: Sequence[str] = folder_db_path.parts
        if parts and parts[0] == "raw":
            parts = parts[1:]
        folder_fs_path = raw_dir_path.joinpath(*parts)

        filename_val = doc.get("filename")
        if not isinstance(filename_val, str) or not filename_val.strip():
            log.warning("NLP skip: filename mancante o non valido", extra={"doc": doc})
            return None

        candidate = folder_fs_path / filename_val
        try:
            return cast(Path, ensure_within_and_resolve(raw_dir_path, candidate))
        except Exception as exc:  # pragma: no cover - defensive guard
            log.warning(
                "NLP skip: percorso non sicuro",
                extra={"doc": doc, "candidate": str(candidate), "error": str(exc)},
            )
            return None

    for doc in docs:
        doc_id_val = doc.get("id")
        try:
            doc_id = int(doc_id_val)
        except (TypeError, ValueError):
            log.warning("ID documento non valido", extra={"doc": doc})
            continue

        folder_id_val = doc.get("folder_id")
        try:
            folder_id_opt = int(folder_id_val) if folder_id_val is not None else None
        except (TypeError, ValueError):
            folder_id_opt = None
        doc_ids_by_folder[folder_id_opt].append(doc_id)

        if only_missing and doc_id in doc_terms_index:
            continue
        if rebuild and doc_id in doc_terms_index:
            clear_doc_terms(conn, doc_id)
            doc_terms_index.discard(doc_id)
        elif rebuild:
            clear_doc_terms(conn, doc_id)

        pdf_path = _abs_path_for(doc)
        if pdf_path is None:
            continue
        if not pdf_path.exists():
            log.warning("NLP skip: file non trovato", extra={"file_path": str(pdf_path)})
            continue

        tasks.append(DocTask(doc_id=doc_id, pdf_path=pdf_path))

    cache = FolderCache(
        paths_by_id=paths_by_id,
        doc_ids_by_folder={k: v for k, v in doc_ids_by_folder.items()},
    )
    return tasks, len(docs), cache


def process_document(
    task: DocTask,
    *,
    lang: str,
    topn_doc: int,
    model: str,
) -> list[tuple[str, float, str]]:
    """Estrae keyword da un singolo documento PDF."""
    from nlp.nlp_keywords import extract_text_from_pdf, fuse_and_dedup, keybert_scores, spacy_candidates, yake_scores

    text = extract_text_from_pdf(str(task.pdf_path))
    cand_spa = spacy_candidates(text, lang=lang)
    sc_y = yake_scores(text, top_k=int(topn_doc) * 2, lang=lang)
    sc_kb = keybert_scores(text, set(cand_spa), model_name=model, top_k=int(topn_doc) * 2)
    fused = fuse_and_dedup(text, cand_spa, sc_y, sc_kb)
    fused.sort(key=lambda x: x[1], reverse=True)
    return [(phrase, score, "ensemble") for phrase, score in fused[: int(topn_doc)]]


def _persist_sections(
    conn: Any,
    *,
    topk_folder: int,
    cluster_thr: float,
    model: str,
    logger: logging.Logger,
    folder_cache: FolderCache,
) -> dict[str, Any]:
    from nlp.nlp_keywords import cluster_synonyms, topn_by_folder

    folder_stats: dict[int, list[tuple[str, float]]] = {}
    doc_to_folder: dict[int, Optional[int]] = {}

    for folder_id, doc_ids in folder_cache.doc_ids_by_folder.items():
        for doc_id in doc_ids:
            doc_to_folder[doc_id] = folder_id

    totals_by_folder: dict[int, dict[str, float]] = {}
    rows = conn.execute("SELECT document_id, phrase, score FROM doc_terms ORDER BY document_id ASC").fetchall()
    for row in rows:
        try:
            doc_id = int(row[0])
        except (TypeError, ValueError):
            continue
        folder_id = doc_to_folder.get(doc_id)
        if folder_id is None:
            continue
        phrase = str(row[1])
        score = float(row[2])
        folder_totals = totals_by_folder.setdefault(folder_id, {})
        folder_totals[phrase] = folder_totals.get(phrase, 0.0) + score

    phrase_global: dict[str, float] = {}
    for fid, phrase_agg in totals_by_folder.items():
        if not phrase_agg:
            continue

        maxv = max(phrase_agg.values())
        if maxv <= 0:
            maxv = 1.0
        norm_items = [(p, (w / maxv)) for p, w in phrase_agg.items()]
        norm_items = topn_by_folder(norm_items, k=int(topk_folder))

        for phrase, weight in norm_items:
            weight_f = float(weight)
            prev = phrase_global.get(phrase)
            if prev is None or weight_f > prev:
                phrase_global[phrase] = weight_f
        folder_stats[fid] = norm_items

        logger.debug("Aggregazione cartella", extra={"folder_id": fid, "terms": len(norm_items)})

    global_list = list(phrase_global.items())
    clusters = cluster_synonyms(global_list, model_name=model, sim_thr=float(cluster_thr))
    if clusters:
        aliases = sum(max(0, len(c.get("synonyms", []) or [])) for c in clusters)
        avg_size = sum(len(c.get("members", []) or []) for c in clusters) / max(1, len(clusters))
        logger.info(
            "Cluster calcolati",
            extra={"k": len(clusters), "avg_size": avg_size, "aliases": aliases},
        )

    phrase_to_tid: dict[str, int] = {}
    terms_count = 0
    alias_count = 0
    for cl in clusters:
        canon = cl["canonical"]
        tid = upsert_term(conn, canon)
        terms_count += 1
        phrase_to_tid[canon] = tid
        for al in cl.get("synonyms", []) or []:
            tags_store.add_term_alias(conn, tid, al)
            alias_count += 1
            phrase_to_tid[al] = tid

    folder_terms_count = 0
    for fid, items in folder_stats.items():
        term_agg: dict[int, float] = {}
        for phrase, weight in items:
            tid = phrase_to_tid.get(phrase)
            if tid is None:
                continue
            term_agg[tid] = term_agg.get(tid, 0.0) + float(weight)

        logger.debug("Aggregazione termini per folder", extra={"folder_id": fid, "terms": len(term_agg)})
        for tid, weight in sorted(term_agg.items(), key=lambda kv: kv[1], reverse=True):
            upsert_folder_term(conn, fid, tid, float(weight), status="keep", note=None)
            folder_terms_count += 1

    return {
        "terms": terms_count,
        "aliases": alias_count,
        "folders": len(folder_stats),
        "folder_terms": folder_terms_count,
    }


def _persist_doc_terms(
    conn: Any,
    tasks: Iterable[DocTask],
    *,
    total_docs: int,
    process_func: Callable[[DocTask], list[tuple[str, float, str]]],
    worker_count: int,
    worker_batch_size: int,
    logger: logging.Logger,
) -> int:
    saved_items = 0
    if worker_count <= 1:
        for idx, task in enumerate(tasks, start=1):
            top_items = process_func(task)
            if top_items:
                tags_store.save_doc_terms(conn, task.doc_id, top_items)
                saved_items += len(top_items)
            if total_docs and idx % 100 == 0:
                logger.info("NLP progress", extra={"processed": idx, "documents": total_docs})
        return saved_items

    executor = ThreadPoolExecutor(max_workers=worker_count)
    pending: deque[tuple[DocTask, Any]] = deque()
    capacity = max(worker_batch_size * worker_count, worker_count)
    idx = 0

    def _drain(queue: deque[tuple[DocTask, Any]], current_index: int) -> int:
        nonlocal saved_items
        task, future = queue.popleft()
        top_items = future.result()
        current_index += 1
        if top_items:
            tags_store.save_doc_terms(conn, task.doc_id, top_items)
            saved_items += len(top_items)
        if total_docs and current_index % 100 == 0:
            logger.info("NLP progress", extra={"processed": current_index, "documents": total_docs})
        return current_index

    try:
        for task in tasks:
            pending.append((task, executor.submit(process_func, task)))
            if len(pending) >= capacity:
                idx = _drain(pending, idx)
        while pending:
            idx = _drain(pending, idx)
    finally:
        executor.shutdown(wait=True)
    return saved_items


def persist_sections(
    conn: Any,
    *,
    topk_folder: int,
    cluster_thr: float,
    model: str,
    logger: logging.Logger,
    folder_cache: FolderCache,
) -> dict[str, Any]:
    """Wrapper pubblico per `_persist_sections`."""
    return _persist_sections(
        conn,
        topk_folder=topk_folder,
        cluster_thr=cluster_thr,
        model=model,
        logger=logger,
        folder_cache=folder_cache,
    )


def run_doc_terms_pipeline(
    conn: Any,
    *,
    raw_dir_path: Path,
    lang: str,
    topn_doc: int,
    topk_folder: int,
    cluster_thr: float,
    model: str,
    only_missing: bool,
    rebuild: bool,
    worker_count: int,
    worker_batch_size: int,
    logger: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    """Esegue l'intera pipeline NLP (doc_terms + clustering) e restituisce statistiche."""
    log = logger or get_structured_logger("semantic.nlp.runner")
    tasks, total_docs, folder_cache = collect_doc_tasks(
        conn,
        raw_dir_path=raw_dir_path,
        only_missing=only_missing,
        rebuild=rebuild,
        logger=log,
    )

    process_func = partial(process_document, lang=lang, topn_doc=topn_doc, model=model)
    saved_items = _persist_doc_terms(
        conn,
        tasks,
        total_docs=total_docs,
        process_func=process_func,
        worker_count=max(1, worker_count),
        worker_batch_size=max(1, worker_batch_size),
        logger=log,
    )

    section_stats = persist_sections(
        conn,
        topk_folder=topk_folder,
        cluster_thr=cluster_thr,
        model=model,
        logger=log,
        folder_cache=folder_cache,
    )

    stats = {
        "documents": total_docs,
        "doc_terms": saved_items,
        **section_stats,
    }
    log.info("semantic.nlp.completed", extra=stats)
    return stats
