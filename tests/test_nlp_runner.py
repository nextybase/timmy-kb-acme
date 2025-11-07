# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from semantic import nlp_runner
from storage.tags_store import ensure_schema_v2, get_conn, save_doc_terms, upsert_document, upsert_folder


class _NoopLogger:
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def debug(self, *args: Any, **kwargs: Any) -> None: ...


def test_collect_doc_tasks_skips_existing_doc_terms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "kb"
    raw_dir = base_dir / "raw"
    nested_raw = raw_dir / "section"
    nested_raw.mkdir(parents=True, exist_ok=True)
    pdf_existing = nested_raw / "existing.pdf"
    pdf_missing = nested_raw / "missing.pdf"
    pdf_existing.write_bytes(b"%PDF-1.4\n%")
    pdf_missing.write_bytes(b"%PDF-1.4\n%")

    db_path = base_dir / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "raw/section", "raw")
        doc_existing = upsert_document(conn, folder_id, pdf_existing.name, sha256="aaa", pages=1)
        doc_missing = upsert_document(conn, folder_id, pdf_missing.name, sha256="bbb", pages=2)
        save_doc_terms(conn, doc_existing, [("alpha", 0.9, "ensemble")])

        tasks, total_docs, cache = nlp_runner.collect_doc_tasks(
            conn,
            raw_dir_path=raw_dir,
            only_missing=True,
            rebuild=False,
            logger=_NoopLogger(),
        )

    assert total_docs == 2
    assert [task.doc_id for task in tasks] == [doc_missing]
    assert cache.paths_by_id[folder_id].as_posix().endswith("raw/section")
    assert tasks[0].pdf_path == pdf_missing.resolve()


def test_persist_sections_clusters_and_upserts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "kb"
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = raw_dir / "alpha.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%")

    db_path = base_dir / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "raw", None)
        doc_id = upsert_document(conn, folder_id, pdf_path.name, sha256="ccc", pages=3)
        save_doc_terms(conn, doc_id, [("gamma", 0.8, "ensemble"), ("beta", 0.5, "ensemble")])

        _, _, cache = nlp_runner.collect_doc_tasks(
            conn,
            raw_dir_path=raw_dir,
            only_missing=False,
            rebuild=False,
            logger=_NoopLogger(),
        )

        monkeypatch.setattr("nlp.nlp_keywords.topn_by_folder", lambda items, k: items)

        def _fake_cluster(items: Any, model_name: str, sim_thr: float) -> list[dict[str, Any]]:
            if not items:
                return []
            canonical, _ = max(items, key=lambda entry: entry[1])
            members = [phrase for phrase, _ in items]
            return [{"canonical": canonical, "members": members, "synonyms": members[1:]}]

        monkeypatch.setattr("nlp.nlp_keywords.cluster_synonyms", _fake_cluster)

        stats = nlp_runner.persist_sections(
            conn,
            topk_folder=5,
            cluster_thr=0.4,
            model="dummy",
            logger=_NoopLogger(),
            folder_cache=cache,
        )

        term_rows = conn.execute("SELECT canonical FROM terms").fetchall()
        folder_term_rows = conn.execute("SELECT term_id FROM folder_terms").fetchall()
        alias_rows = conn.execute("SELECT alias FROM term_aliases").fetchall()

    assert stats["terms"] >= 1
    assert term_rows
    assert folder_term_rows
    assert alias_rows


def test_run_doc_terms_pipeline_processes_and_returns_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "kb"
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = raw_dir / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%")

    db_path = base_dir / "semantic" / "tags.db"
    ensure_schema_v2(str(db_path))

    with get_conn(str(db_path)) as conn:
        folder_id = upsert_folder(conn, "raw", None)
        doc_id = upsert_document(conn, folder_id, pdf_path.name, sha256="ddd", pages=1)

        processed: list[int] = []

        def _fake_process(
            task: nlp_runner.DocTask,
            *,
            lang: str,
            topn_doc: int,
            model: str,
        ) -> list[tuple[str, float, str]]:
            processed.append(task.doc_id)
            return [("omega", 0.7, "ensemble")]

        monkeypatch.setattr(nlp_runner, "process_document", _fake_process)
        monkeypatch.setattr("nlp.nlp_keywords.topn_by_folder", lambda items, k: items)
        monkeypatch.setattr(
            "nlp.nlp_keywords.cluster_synonyms",
            lambda items, model_name, sim_thr: [{"canonical": items[0][0], "members": [items[0][0]], "synonyms": []}],
        )

        stats = nlp_runner.run_doc_terms_pipeline(
            conn,
            raw_dir_path=raw_dir,
            lang="it",
            topn_doc=5,
            topk_folder=3,
            cluster_thr=0.3,
            model="dummy",
            only_missing=False,
            rebuild=False,
            worker_count=1,
            worker_batch_size=2,
        )

        doc_terms_rows = conn.execute("SELECT document_id, phrase FROM doc_terms").fetchall()
        terms_rows = conn.execute("SELECT canonical FROM terms").fetchall()

    assert processed == [doc_id]
    assert stats["documents"] == 1
    assert stats["doc_terms"] == 1
    assert doc_terms_rows
    assert terms_rows
