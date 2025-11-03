# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import timmykb.kb_db as kb


def test_insert_chunks_logs_db_inserted_and_idempotent(tmp_path: Path, caplog):
    db = tmp_path / "kb.sqlite"
    kb.init_db(db)

    project, scope, path, version = "p", "s", "file.md", "v1"
    meta = {"source": "t"}
    chunks = ["A", "B"]
    embeddings = [[1.0], [1.0]]

    caplog.set_level(logging.INFO)
    n1 = kb.insert_chunks(project, scope, path, version, meta, chunks, embeddings, db_path=db)
    recs = [r for r in caplog.records if r.msg == "semantic.index.db_inserted"]
    assert recs and getattr(recs[-1], "inserted", None) == 2
    assert getattr(recs[-1], "rows", None) == 2
    assert n1 == 2

    caplog.clear()
    n2 = kb.insert_chunks(project, scope, path, version, meta, chunks, embeddings, db_path=db)
    recs2 = [r for r in caplog.records if r.msg == "semantic.index.db_inserted"]
    assert recs2 and getattr(recs2[-1], "inserted", None) == 0
    assert n2 == 0


def test_fetch_candidates_logs_invalid_json(tmp_path: Path, caplog):
    db = tmp_path / "kb.sqlite"
    kb.init_db(db)
    now = datetime.utcnow().isoformat()
    project, scope = "proj", "book"
    with kb.connect(db) as con:
        con.execute(
            "INSERT INTO chunks (project_slug, scope, path, version, meta_json, content, embedding_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project, scope, "p1", "v", "{invalid", "c1", "[1,2,3]", now),
        )
        con.execute(
            "INSERT INTO chunks (project_slug, scope, path, version, meta_json, content, embedding_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project, scope, "p2", "v", "{}", "c2", "not_json", now),
        )
        con.commit()

    caplog.set_level(logging.WARNING)
    list(kb.fetch_candidates(project, scope, limit=10, db_path=db))
    msgs = [r.msg for r in caplog.records]
    assert "kb_db.fetch.invalid_meta_json" in msgs
    assert "kb_db.fetch.invalid_embedding_json" in msgs
    mrec = next(r for r in caplog.records if r.msg == "kb_db.fetch.invalid_meta_json")
    erec = next(r for r in caplog.records if r.msg == "kb_db.fetch.invalid_embedding_json")
    assert getattr(mrec, "project_slug", None) == project
    assert getattr(erec, "scope", None) == scope
