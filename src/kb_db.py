"""Lightweight SQLite storage for Timmy KB.

Exposes:
- insert_chunks(project_slug, scope, path, version, meta_dict, chunks, embeddings)
- fetch_candidates(project_slug, scope, limit=64)

This module centralizes DB path handling and initialization. Embeddings are
stored as JSON arrays for portability. Uses WAL mode to reduce lock contention.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional


LOGGER = logging.getLogger("timmy_kb.kb_db")


DEFAULT_DATA_DIR = Path("data")
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "kb.sqlite"


def ensure_data_dir(path: Path | str = DEFAULT_DATA_DIR) -> Path:
    """Ensure the data directory exists and return it."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db_path() -> Path:
    """Return the SQLite DB path (ensures parent dir)."""
    ensure_data_dir(DEFAULT_DATA_DIR)
    return DEFAULT_DB_PATH


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Context manager for SQLite connection with sane PRAGMAs."""
    dbp = Path(db_path) if db_path else get_db_path()
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(dbp), timeout=30, check_same_thread=False)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        yield con
    finally:
        con.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Create tables and indexes if missing."""
    with connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_slug TEXT NOT NULL,
                scope TEXT NOT NULL,
                path TEXT NOT NULL,
                version TEXT,
                meta_json TEXT,
                content TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_project_scope
            ON chunks(project_slug, scope);
            """
        )
        con.commit()
    LOGGER.debug("DB initialized at %s", (db_path or get_db_path()))


def insert_chunks(
    project_slug: str,
    scope: str,
    path: str,
    version: str,
    meta_dict: Dict,
    chunks: List[str],
    embeddings: List[List[float]],
    db_path: Optional[Path] = None,
) -> int:
    """Insert chunk+embedding rows. Returns number of rows inserted.

    Raises ValueError if lengths mismatch.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length mismatch")
    init_db(db_path)
    now = datetime.utcnow().isoformat()
    rows = [
        (
            project_slug,
            scope,
            path,
            version,
            json.dumps(meta_dict, ensure_ascii=False),
            chunk,
            json.dumps(vec),
            now,
        )
        for chunk, vec in zip(chunks, embeddings)
    ]
    with connect(db_path) as con:
        cur = con.executemany(
            """
            INSERT INTO chunks (
                project_slug, scope, path, version, meta_json, content, embedding_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.commit()
        inserted = cur.rowcount if cur.rowcount is not None else len(rows)
    LOGGER.info("Inserted %d chunks for %s/%s from %s", inserted, project_slug, scope, path)
    return inserted


def fetch_candidates(
    project_slug: str,
    scope: str,
    limit: int = 64,
    db_path: Optional[Path] = None,
) -> Iterator[Dict]:
    """Yield candidate rows for a (project_slug, scope).

    Each yielded dict has: content(str), meta(dict), embedding(list[float]).
    Ordered by newest first. LIMIT is applied at SQL level.
    """
    init_db(db_path)
    sql = (
        "SELECT content, meta_json, embedding_json FROM chunks "
        "WHERE project_slug = ? AND scope = ? ORDER BY id DESC LIMIT ?"
    )
    with connect(db_path) as con:
        for content, meta_json, emb_json in con.execute(sql, (project_slug, scope, int(limit))):
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except json.JSONDecodeError:
                meta = {}
            try:
                emb = json.loads(emb_json)
            except json.JSONDecodeError:
                emb = []
            yield {"content": content, "meta": meta, "embedding": emb}
