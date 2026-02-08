# SPDX-License-Identifier: GPL-3.0-or-later
# src/storage/kb_db.py
"""Archivio SQLite leggero per Timmy KB.

Espone:
- insert_chunks(slug, scope, path, version, meta_dict, chunks, embeddings)
- fetch_candidates(slug, scope, limit=64)

Questo modulo centralizza la gestione del path del DB e l'inizializzazione.
Il contratto sul path e' formalizzato in `storage.kb_store.KbStore`, che risolve
gia' i DB per workspace/slug (default: <workspace>/semantic/kb.sqlite).
Le embedding sono salvate come array JSON per portabilita'. Usa la modalita' WAL
per ridurre la contesa dei lock.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Optional

from pipeline.beta_flags import is_beta_strict
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

if TYPE_CHECKING:
    from storage.kb_store import KbStore

LOGGER = get_structured_logger("timmy_kb.kb_db")
# I logger strutturati aggiungono sempre un console handler; sul percorso hot-path (indexer)
# alziamo il livello per evitare I/O ripetuti ma lasciamo comunque propagare gli INFO.
for _handler in list(LOGGER.handlers):
    key = getattr(_handler, "_logging_utils_key", "")
    if key.endswith("::console"):
        _handler.setLevel(logging.WARNING)

_LEGACY_GLOBAL_DB_PARTS = ("data", "kb.sqlite")


def _resolve_db_path(db_path: Optional[Path]) -> Path:
    """Risoluzione sicura del path DB.

    Regole:
    - `db_path` e' obbligatorio e deve essere esplicito.
    - Deve essere un path assoluto (derivato da WorkspaceLayout/ClientContext).
    """
    if db_path is None:
        raise ConfigError(
            "db_path must be provided explicitly via WorkspaceLayout / ClientContext. "
            "Implicit CWD-based resolution is forbidden.",
            code="kb.db_path.missing",
            component="kb_db",
        )
    p = Path(db_path)
    if not p.is_absolute():
        raise ConfigError(
            "db_path must be absolute and derived from WorkspaceLayout / ClientContext.",
            code="kb.db_path.relative",
            component="kb_db",
            file_path=str(p),
        )
    resolved = p.resolve()
    if resolved.parts[-2:] == _LEGACY_GLOBAL_DB_PARTS:
        raise ConfigError(
            "DB globale legacy `data/kb.sqlite` non supportato: usa `<workspace>/semantic/kb.sqlite`.",
            code="kb.db_path.legacy",
            component="kb_db",
            file_path=str(resolved),
        )
    return resolved


def connect_from_store(store: "KbStore") -> Iterator[sqlite3.Connection]:
    """Convenience wrapper: apre una connessione usando il path risolto da KbStore.

    Se lo store e' legato a un workspace/slug, usa `repo_root_dir/semantic/kb.sqlite`;
    in assenza di repo_root_dir o override, fallisce (nessuna risoluzione globale implicita).
    """
    return connect(db_path=store.effective_db_path())


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
            message = str(e)
            if "malformed" in message.lower():
                raise ConfigError(
                    "DB SQLite corrotto (malformed): elimina/rigenera il DB del workspace prima di procedere.",
                    code="kb.db.malformed",
                    component="kb_db",
                    file_path=str(dbp),
                ) from e
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
                slug TEXT NOT NULL,
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
        # Crea un indice composito per ricerche rapide su slug e scope
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_slug_scope
            ON chunks(slug, scope);
            """
        )
        # Indice UNIQUE per idempotenza su chiave naturale (slug, scope, path, version, content)
        # Strict init: su IntegrityError l'inizializzazione fallisce immediatamente, indicando la necessità
        # di rigenerare il DB (non c'è recover o warn).
        try:
            con.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_natural
                ON chunks(slug, scope, path, version, content);
                """
            )
        except sqlite3.IntegrityError:
            raise ConfigError(
                "DB KB non conforme: duplicati presenti e indice UNIQUE non applicabile. "
                "Rigenera il DB del workspace prima di procedere.",
                code="kb.db.schema.invalid",
                component="kb_db",
                file_path=str(_resolve_db_path(db_path)),
            )
        con.commit()
    LOGGER.debug(
        "kb_db.initialized",
        extra={"db_path": str(_resolve_db_path(db_path))},
    )


def insert_chunks(
    slug: str,
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
            slug,
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
            "INSERT INTO chunks (slug, scope, path, version, meta_json, content, embedding_json, created_at) "
            "SELECT ?, ?, ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM chunks WHERE slug=? AND scope=? AND path=? AND version=? AND content=? LIMIT 1"
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
            "slug": slug,
            "scope": scope,
            "path": path,
            "version": version,
            "rows": len(rows),
            "inserted": inserted,
        },
    )
    return inserted


def fetch_candidates(
    slug: str,
    scope: str,
    limit: int = 64,
    db_path: Optional[Path] = None,
    *,
    strict_mode: bool | None = None,
) -> Iterator[dict[str, Any]]:
    """Restituisce (iterator) i candidati per (slug, scope).

    Ogni dict prodotto contiene: content (str), meta (dict), embedding (list[float]).
    Ordinati dal più recente. Il LIMIT è applicato a livello SQL.
    """
    resolved_db_path = _resolve_db_path(db_path)
    init_db(resolved_db_path)
    sql = (
        "SELECT content, meta_json, embedding_json FROM chunks " "WHERE slug = ? AND scope = ? ORDER BY id DESC LIMIT ?"
    )
    strict = is_beta_strict() if strict_mode is None else strict_mode
    with connect(resolved_db_path) as con:
        for content, meta_json, emb_json in con.execute(sql, (slug, scope, int(limit))):
            corrupted = False
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except json.JSONDecodeError:
                corrupted = True
                _handle_corrupted_fetch(
                    slug=slug,
                    scope=scope,
                    field="meta_json",
                    event="kb_db.fetch.invalid_meta_json",
                    strict=strict,
                )
            try:
                emb = json.loads(emb_json) if emb_json else []
            except json.JSONDecodeError:
                corrupted = True
                _handle_corrupted_fetch(
                    slug=slug,
                    scope=scope,
                    field="embedding_json",
                    event="kb_db.fetch.invalid_embedding_json",
                    strict=strict,
                )
            if corrupted:
                continue
            yield {"content": content, "meta": meta, "embedding": emb}


def _handle_corrupted_fetch(slug: str, scope: str, field: str, event: str, *, strict: bool) -> None:
    """Logga o fallisce in base alla modalità strict."""
    extra = {
        "slug": slug,
        "scope": scope,
        "service_only": True,
        "field": field,
    }
    if strict:
        raise ConfigError(
            f"Invalid {field} JSON for slug={slug} scope={scope}.",
            code=f"kb.db.fetch.invalid_{field}",
            component="kb_db",
        )
    LOGGER.warning(event, extra=extra)
