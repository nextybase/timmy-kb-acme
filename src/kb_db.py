# SPDX-License-Identifier: GPL-3.0-only
# src/kb_db.py
"""Archivio SQLite leggero per Timmy KB.

Espone:
- insert_chunks(project_slug, scope, path, version, meta_dict, chunks, embeddings)
- fetch_candidates(project_slug, scope, limit=64)

Questo modulo centralizza la gestione del path del DB e l'inizializzazione.
Le embedding sono salvate come array JSON per portabilità. Usa la modalità WAL
per ridurre la contesa dei lock.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional, cast

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve

LOGGER = get_structured_logger("timmy_kb.kb_db")
# I logger strutturati aggiungono sempre un console handler; sul percorso hot-path (indexer)
# alziamo il livello per evitare I/O ripetuti ma lasciamo comunque propagare gli INFO.
for _handler in list(LOGGER.handlers):
    key = getattr(_handler, "_logging_utils_key", "")
    if key.endswith("::console"):
        _handler.setLevel(logging.WARNING)

DEFAULT_DATA_DIR = Path("data")
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "kb.sqlite"


def ensure_data_dir(path: Path | str = DEFAULT_DATA_DIR) -> Path:
    """Garantisce l'esistenza della cartella dati e la restituisce."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_db_path(db_path: Optional[Path]) -> Path:
    """Risoluzione sicura del path DB.

    Regole:
    - Se `db_path` è None: usa `data/kb.sqlite` e valida che resti sotto `data/`.
    - Se `db_path` è assoluto: usa il path risolto così com'è (compatibilità test/override).
    - Se `db_path` è relativo: interpretalo sotto `data/` e valida che resti entro il perimetro.
    """
    if db_path is None:
        ensure_data_dir(DEFAULT_DATA_DIR)
        return cast(Path, ensure_within_and_resolve(DEFAULT_DATA_DIR, DEFAULT_DB_PATH))
    p = Path(db_path)
    if p.is_absolute():
        return p.resolve()
    # relativo: ancora a data/
    ensure_data_dir(DEFAULT_DATA_DIR)
    candidate = (DEFAULT_DATA_DIR / p).resolve()
    return cast(Path, ensure_within_and_resolve(DEFAULT_DATA_DIR, candidate))


def get_db_path() -> Path:
    """Restituisce il path del DB SQLite predefinito sotto `data/` (crea la cartella se manca)."""
    return _resolve_db_path(None)


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Context manager per una connessione SQLite con PRAGMA adeguati."""
    dbp = _resolve_db_path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(dbp), timeout=30, check_same_thread=False)
    try:
        # Configurazioni di performance e integrità
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA foreign_keys=ON;")
        except sqlite3.DatabaseError as e:
            if "malformed" in str(e).lower():
                try:
                    con.close()
                except Exception:
                    pass
                try:
                    backup = dbp.with_suffix(dbp.suffix + ".bak")
                    if dbp.exists():
                        dbp.replace(backup)
                    LOGGER.warning("db.malformed.recreated", extra={"db_path": str(dbp), "backup": str(backup)})
                except Exception:
                    pass
                con = sqlite3.connect(str(dbp), timeout=30, check_same_thread=False)
                con.execute("PRAGMA journal_mode=WAL;")
                con.execute("PRAGMA synchronous=NORMAL;")
                con.execute("PRAGMA foreign_keys=ON;")
            else:
                raise
        yield con
    finally:
        con.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Crea tabelle e indici se mancanti."""
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
        # Crea un indice composito per ricerche rapide su progetto e scope
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_project_scope
            ON chunks(project_slug, scope);
            """
        )
        # Indice UNIQUE per idempotenza su chiave naturale (project, scope, path, version, content)
        # Safe-migration: se esistono già duplicati, la creazione fallisce -> log warning e prosegui.
        try:
            con.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_natural
                ON chunks(project_slug, scope, path, version, content);
                """
            )
        except sqlite3.IntegrityError:
            LOGGER.warning("Migrazione UNIQUE ux_chunks_natural saltata: duplicati presenti")
        con.commit()
    LOGGER.debug("DB inizializzato in %s", (db_path or get_db_path()))


def insert_chunks(
    project_slug: str,
    scope: str,
    path: str,
    version: str,
    meta_dict: dict[str, Any],
    chunks: list[str],
    embeddings: list[list[float]],
    db_path: Optional[Path] = None,
    *,
    ensure_schema: bool = True,
) -> int:
    """Inserisce righe (chunk + embedding). Restituisce il numero **effettivo** di righe inserite.

    Solleva ValueError se le lunghezze di chunks ed embeddings non coincidono.
    """
    if len(chunks) != len(embeddings):
        raise ValueError("il numero di chunks non coincide con il numero di embeddings")
    if ensure_schema:
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
            json.dumps(vec, ensure_ascii=False),
            now,
        )
        for chunk, vec in zip(chunks, embeddings, strict=False)
    ]
    with connect(db_path) as con:
        sql = (
            "INSERT INTO chunks (project_slug, scope, path, version, meta_json, content, embedding_json, created_at) "
            "SELECT ?, ?, ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM chunks WHERE project_slug=? AND scope=? AND path=? AND version=? AND content=? LIMIT 1"
            ")"
        )
        params = [(pr, sc, pa, ve, mj, co, ej, ts, pr, sc, pa, ve, co) for (pr, sc, pa, ve, mj, co, ej, ts) in rows]
        before = int(con.total_changes)
        con.executemany(sql, params)
        con.commit()
        inserted = int(con.total_changes) - before  # numero reale di nuove righe
    LOGGER.info(
        "semantic.index.db_inserted",
        extra={
            "project_slug": project_slug,
            "scope": scope,
            "path": path,
            "version": version,
            "rows": len(rows),
            "inserted": inserted,
        },
    )
    return inserted


def fetch_candidates(
    project_slug: str,
    scope: str,
    limit: int = 64,
    db_path: Optional[Path] = None,
) -> Iterator[dict[str, Any]]:
    """Restituisce (iterator) i candidati per (project_slug, scope).

    Ogni dict prodotto contiene: content (str), meta (dict), embedding (list[float]).
    Ordinati dal più recente. Il LIMIT è applicato a livello SQL.
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
                LOGGER.warning(
                    "kb_db.fetch.invalid_meta_json",
                    extra={"slug": project_slug, "scope": scope},
                )
            try:
                emb = json.loads(emb_json) if emb_json else []
            except json.JSONDecodeError:
                emb = []
                LOGGER.warning(
                    "kb_db.fetch.invalid_embedding_json",
                    extra={"slug": project_slug, "scope": scope},
                )
            yield {"content": content, "meta": meta, "embedding": emb}
