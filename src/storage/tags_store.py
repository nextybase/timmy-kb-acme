# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

__all__ = [
    "load_tags_reviewed",
    "save_tags_reviewed",
    "derive_db_path_from_yaml_path",
    "ensure_schema_v2",
    "DocEntityRecord",
    "save_doc_entities",
    "list_doc_entities",
    # v2 helpers
    "get_conn",
    "upsert_folder",
    "upsert_document",
    "get_folder_by_path",
    "list_folders",
    "upsert_term",
    "add_term_alias",
    "get_term_by_canonical",
    "list_term_aliases",
    "save_doc_terms",
    "upsert_folder_term",
    "get_folder_terms",
    "set_folder_term_status",
    "log_edit",
    "list_documents",
    "get_document_by_id",
    "has_doc_terms",
    "clear_doc_terms",
    "get_folder_id_for_document",
    "get_documents_by_folder",
]

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

LOG = get_structured_logger("storage.tags_store")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta(
          id INTEGER PRIMARY KEY CHECK (id=1),
          version TEXT NOT NULL,
          reviewed_at TEXT NOT NULL,
          keep_only_listed INTEGER NOT NULL CHECK (keep_only_listed IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS tags(
          id INTEGER PRIMARY KEY,
          name TEXT UNIQUE NOT NULL,
          action TEXT NOT NULL,
          note TEXT
        );
        CREATE TABLE IF NOT EXISTS tag_synonyms(
          tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
          alias TEXT NOT NULL,
          pos INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(tag_id, alias)
        );
        """)


def _to_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    try:
        return bool(int(x))
    except Exception:
        return str(x).strip().lower() in {"1", "true", "yes", "on"}


def _to_int(x: Any) -> int:
    return 1 if _to_bool(x) else 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def derive_db_path_from_yaml_path(p: str | Path) -> str:
    """Dato il path YAML (es.

    `semantic/tags_reviewed.yaml`), ritorna il path DB
    adiacente `tags.db`.
    """
    pp = Path(p)
    if pp.parent.name != "semantic":
        raise ConfigError(
            "Percorso tags_reviewed non valido: il file deve stare sotto `<workspace>/semantic/`.",
            file_path=str(pp),
        )
    return str(pp.parent / "tags.db")


def load_tags_reviewed(db_path: str) -> dict[str, Any]:
    """Carica il vocabolario rivisto da SQLite e ritorna la struttura SSoT."""
    dbp = Path(db_path)
    if not dbp.parent.exists():
        dbp.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(dbp)) as conn:
        _ensure_schema(conn)

        # meta
        cur = conn.execute("SELECT version, reviewed_at, keep_only_listed FROM meta WHERE id=1")
        row = cur.fetchone()
        if row is None:
            version = "2"
            reviewed_at = _now_iso()
            keep_only_listed = False
        else:
            version = str(row[0])
            reviewed_at = str(row[1])
            keep_only_listed = _to_bool(row[2])

        # tags
        tags: list[dict[str, Any]] = []
        cur = conn.execute("SELECT id, name, action, note FROM tags ORDER BY name COLLATE NOCASE ASC")
        for tid, name, action, note in cur.fetchall():
            syns_cur = conn.execute(
                ("SELECT alias FROM tag_synonyms WHERE tag_id=? " "ORDER BY pos ASC, alias COLLATE NOCASE ASC"),
                (tid,),
            )
            syns = [str(r[0]) for r in syns_cur.fetchall()]
            tags.append(
                {
                    "name": str(name),
                    "action": str(action),
                    "synonyms": syns,
                    "note": None if note is None else str(note),
                }
            )

        return {
            "version": version,
            "reviewed_at": reviewed_at,
            "keep_only_listed": bool(keep_only_listed),
            "tags": tags,
        }


def save_tags_reviewed(db_path: str, data: dict[str, Any]) -> None:
    """Persiste in SQLite (upsert) lo stesso dict precedentemente scritto in YAML."""
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(dbp)) as conn:
        try:
            _ensure_schema(conn)
            conn.execute("BEGIN")

            # Upsert meta (id=1)
            version = str((data or {}).get("version") or "2")
            reviewed_at = str((data or {}).get("reviewed_at") or _now_iso())
            keep_only_listed = _to_int((data or {}).get("keep_only_listed", False))
            conn.execute(
                (
                    "INSERT INTO meta(id, version, reviewed_at, keep_only_listed) "
                    "VALUES(1, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "version=excluded.version, reviewed_at=excluded.reviewed_at, "
                    "keep_only_listed=excluded.keep_only_listed"
                ),
                (version, reviewed_at, keep_only_listed),
            )

            # Rebuild tags and synonyms from incoming data
            conn.execute("DELETE FROM tag_synonyms")
            conn.execute("DELETE FROM tags")

            items = (data or {}).get("tags") or []
            if not isinstance(items, list):
                items = []

            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                action = str(item.get("action", "")).strip()
                note_val = item.get("note")
                cur = conn.execute(
                    "INSERT INTO tags(name, action, note) VALUES(?, ?, ?)",
                    (name, action, None if note_val is None else str(note_val)),
                )
                tid = cur.lastrowid
                syns = item.get("synonyms") or []
                try:
                    for pos, alias in enumerate([str(s).strip() for s in syns if str(s).strip()], start=0):
                        conn.execute(
                            ("INSERT OR IGNORE INTO tag_synonyms(tag_id, alias, pos) " "VALUES(?, ?, ?)"),
                            (tid, alias, pos),
                        )
                except TypeError:
                    pass

            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _create_v2_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS folders(
          id INTEGER PRIMARY KEY,
          path TEXT UNIQUE NOT NULL,
          parent_id INTEGER REFERENCES folders(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS documents(
          id INTEGER PRIMARY KEY,
          folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
          filename TEXT NOT NULL,
          sha256 TEXT,
          pages INTEGER,
          UNIQUE(folder_id, filename)
        );
        CREATE TABLE IF NOT EXISTS terms(
          id INTEGER PRIMARY KEY,
          canonical TEXT NOT NULL,
          lang TEXT DEFAULT 'it',
          UNIQUE(canonical, lang)
        );
        CREATE TABLE IF NOT EXISTS term_aliases(
          id INTEGER PRIMARY KEY,
          term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
          alias TEXT NOT NULL,
          UNIQUE(term_id, alias)
        );
        CREATE TABLE IF NOT EXISTS doc_terms(
          document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          phrase TEXT NOT NULL,
          score REAL NOT NULL,
          method TEXT NOT NULL,
          PRIMARY KEY(document_id, phrase)
        );
        CREATE TABLE IF NOT EXISTS folder_terms(
          folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
          term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
          weight REAL NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'keep',
          note TEXT,
          PRIMARY KEY(folder_id, term_id)
        );
        CREATE TABLE IF NOT EXISTS edit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor TEXT NOT NULL,
          entity TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          action TEXT NOT NULL,
          before TEXT,
          after  TEXT,
          ts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_docs_folder ON documents(folder_id);
        CREATE INDEX IF NOT EXISTS idx_ft_folder ON folder_terms(folder_id, term_id);
        CREATE INDEX IF NOT EXISTS idx_terms_canon ON terms(canonical);

        CREATE TABLE IF NOT EXISTS doc_entities(
          id INTEGER PRIMARY KEY,
          doc_uid TEXT NOT NULL,
          area_key TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          confidence REAL NOT NULL,
          origin TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'suggested' CHECK (status IN ('suggested','approved','rejected')),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(doc_uid, area_key, entity_id, origin)
        );
        CREATE INDEX IF NOT EXISTS idx_doc_entities_doc ON doc_entities(doc_uid);
        CREATE INDEX IF NOT EXISTS idx_doc_entities_area ON doc_entities(area_key);
        CREATE INDEX IF NOT EXISTS idx_doc_entities_entity ON doc_entities(entity_id);
        CREATE INDEX IF NOT EXISTS idx_doc_entities_status ON doc_entities(status);
        """)


_V2_TABLES = [
    "folders",
    "documents",
    "terms",
    "term_aliases",
    "doc_terms",
    "folder_terms",
    "edit_log",
    "doc_entities",
]


def ensure_schema_v2(db_path: str) -> None:
    """Garantisce lo schema v2 e fallisce se rileva un DB legacy.

    Regola:
    - Se il file DB esiste già, deve contenere `meta(id=1)` con `version == '2'`.
      In caso contrario solleva ConfigError (nessuna migrazione implicita).
    - Se il file DB non esiste, crea lo schema e imposta `meta.version='2'`.
    """
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    existed = dbp.exists()
    with closing(sqlite3.connect(dbp)) as conn:
        try:
            if existed:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'",
                )
                if cur.fetchone() is None:
                    raise ConfigError(
                        "legacy tags.db detected; regenerate <workspace>/semantic/tags.db",
                        file_path=str(dbp),
                    )
                cur = conn.execute("SELECT version FROM meta WHERE id=1")
                row = cur.fetchone()
                if row is None:
                    raise ConfigError(
                        "legacy tags.db detected; regenerate <workspace>/semantic/tags.db",
                        file_path=str(dbp),
                    )
                version = str(row[0])
                if version != "2":
                    raise ConfigError(
                        "legacy tags.db detected; regenerate <workspace>/semantic/tags.db",
                        file_path=str(dbp),
                    )

            conn.execute("BEGIN")
            _ensure_schema(conn)
            _create_v2_tables(conn)
            conn.execute(
                "INSERT INTO meta(id, version, reviewed_at, keep_only_listed) "
                "VALUES(1, '2', ?, 0) "
                "ON CONFLICT(id) DO UPDATE SET version='2'",
                (_now_iso(),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@dataclass(frozen=True)
class DocEntityRecord:
    doc_uid: str
    area_key: str
    entity_id: str
    confidence: float
    origin: str
    status: str = "suggested"
    created_at: str | None = None
    updated_at: str | None = None


@contextmanager
def get_conn(db_path: str) -> Iterator[sqlite3.Connection]:
    """Ritorna una connessione con row_factory=sqlite3.Row e FK abilitate."""
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


def upsert_folder(conn: sqlite3.Connection, path: str, parent_path: str | None = None) -> int:
    parent_id = None
    if parent_path:
        # Crea/recupera il parent ricorsivamente
        row = conn.execute("SELECT id FROM folders WHERE path=?", (parent_path,)).fetchone()
        if row is None:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    ("INSERT INTO folders(path, parent_id) VALUES(?, NULL) " "ON CONFLICT(path) DO NOTHING"),
                    (parent_path,),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            row = conn.execute("SELECT id FROM folders WHERE path=?", (parent_path,)).fetchone()
        parent_id = int(row[0]) if row else None

    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO folders(path, parent_id) VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET parent_id=excluded.parent_id",
            (path, parent_id),
        )
        # Recupera id
        rid = conn.execute("SELECT id FROM folders WHERE path=?", (path,)).fetchone()
        conn.commit()
        return int(rid[0])
    except Exception:
        conn.rollback()
        raise


def upsert_document(
    conn: sqlite3.Connection,
    folder_id: int,
    filename: str,
    sha256: str | None = None,
    pages: int | None = None,
) -> int:
    conn.execute("BEGIN")
    try:
        conn.execute(
            (
                "INSERT INTO documents(folder_id, filename, sha256, pages) "
                "VALUES(?, ?, ?, ?) "
                "ON CONFLICT(folder_id, filename) DO UPDATE SET "
                "sha256=excluded.sha256, pages=excluded.pages"
            ),
            (folder_id, filename, sha256, pages),
        )
        rid = conn.execute(
            "SELECT id FROM documents WHERE folder_id=? AND filename=?",
            (folder_id, filename),
        ).fetchone()
        conn.commit()
        return int(rid[0])
    except Exception:
        conn.rollback()
        raise


def get_folder_by_path(conn: sqlite3.Connection, path: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT id, path, parent_id FROM folders WHERE path=?", (path,)).fetchone()
    return dict(row) if row else None


def list_folders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT id, path, parent_id FROM folders ORDER BY path")
    return [dict(r) for r in cur.fetchall()]


# ----- terms / term_aliases -----
def upsert_term(conn: sqlite3.Connection, canonical: str, lang: str = "it") -> int:
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO terms(canonical, lang) VALUES(?, ?) "
            "ON CONFLICT(canonical, lang) DO UPDATE SET canonical=excluded.canonical",
            (canonical, lang),
        )
        rid = conn.execute(
            "SELECT id FROM terms WHERE canonical=? AND lang=?",
            (canonical, lang),
        ).fetchone()
        conn.commit()
        return int(rid[0])
    except Exception:
        conn.rollback()
        raise


def add_term_alias(conn: sqlite3.Connection, term_id: int, alias: str) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT OR IGNORE INTO term_aliases(term_id, alias) VALUES(?, ?)",
            (term_id, alias),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_term_by_canonical(conn: sqlite3.Connection, canonical: str, lang: str = "it") -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, canonical, lang FROM terms WHERE canonical=? AND lang=?",
        (canonical, lang),
    ).fetchone()
    return dict(row) if row else None


def list_term_aliases(conn: sqlite3.Connection, term_id: int) -> list[str]:
    cur = conn.execute(
        "SELECT alias FROM term_aliases WHERE term_id=? ORDER BY alias COLLATE NOCASE",
        (term_id,),
    )
    return [str(r[0]) for r in cur.fetchall()]


# ----- doc_terms -----
def save_doc_terms(conn: sqlite3.Connection, document_id: int, items: list[tuple[str, float, str]]) -> None:
    """Items = [(phrase, score, method)] -> upsert su doc_terms."""
    conn.execute("BEGIN")
    try:
        for phrase, score, method in items or []:
            conn.execute(
                (
                    "INSERT INTO doc_terms(document_id, phrase, score, method) "
                    "VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(document_id, phrase) DO UPDATE SET "
                    "score=excluded.score, method=excluded.method"
                ),
                (document_id, phrase, float(score), method),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def save_doc_entities(db_path: str | Path, records: list[DocEntityRecord]) -> None:
    """Inserisce/aggiorna record doc_entities a livello documento."""
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    ensure_schema_v2(str(dbp))

    now = _now_iso()
    with closing(sqlite3.connect(dbp)) as conn:
        conn.execute("BEGIN")
        try:
            for rec in records or []:
                created = rec.created_at or now
                updated = rec.updated_at or now
                conn.execute(
                    (
                        "INSERT INTO doc_entities("
                        "doc_uid, area_key, entity_id, confidence, origin, status, created_at, updated_at"
                        ") VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(doc_uid, area_key, entity_id, origin) DO UPDATE SET "
                        "confidence=excluded.confidence, "
                        "status=excluded.status, "
                        "updated_at=excluded.updated_at"
                    ),
                    (
                        rec.doc_uid,
                        rec.area_key,
                        rec.entity_id,
                        float(rec.confidence),
                        rec.origin,
                        rec.status,
                        created,
                        updated,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_doc_entities(
    db_path: str | Path,
    *,
    doc_uid: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Ritorna i record doc_entities filtrati per doc_uid/status (se forniti)."""
    dbp = Path(db_path)
    if not dbp.exists():
        return []
    ensure_schema_v2(str(dbp))

    with closing(sqlite3.connect(dbp)) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        query = (
            "SELECT doc_uid, area_key, entity_id, confidence, origin, status, created_at, updated_at FROM doc_entities"
        )
        params: list[Any] = []
        clauses: list[str] = []
        if doc_uid:
            clauses.append("doc_uid=?")
            params.append(doc_uid)
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY doc_uid, area_key, entity_id"
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "doc_uid": str(r[0]),
                "area_key": str(r[1]),
                "entity_id": str(r[2]),
                "confidence": float(r[3]),
                "origin": str(r[4]),
                "status": str(r[5]),
                "created_at": str(r[6]),
                "updated_at": str(r[7]),
            }
            for r in rows
        ]


# ----- folder_terms (aggregazione/HiTL) -----
def upsert_folder_term(
    conn: sqlite3.Connection,
    folder_id: int,
    term_id: int,
    weight: float,
    status: str = "keep",
    note: str | None = None,
) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            (
                "INSERT INTO folder_terms(folder_id, term_id, weight, status, note) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(folder_id, term_id) DO UPDATE SET "
                "weight=excluded.weight, status=excluded.status, note=excluded.note"
            ),
            (folder_id, term_id, float(weight), status, note),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_folder_terms(
    conn: sqlite3.Connection, folder_id: int, status: str = "keep", limit: int | None = None
) -> list[tuple[str, float]]:
    sql = (
        "SELECT t.canonical, ft.weight FROM folder_terms ft "
        "JOIN terms t ON t.id=ft.term_id WHERE ft.folder_id=? AND ft.status=? "
        "ORDER BY ft.weight DESC"
    )
    params: list[Any] = [folder_id, status]
    if isinstance(limit, int) and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    cur = conn.execute(sql, tuple(params))
    return [(str(r[0]), float(r[1])) for r in cur.fetchall()]


def set_folder_term_status(conn: sqlite3.Connection, folder_id: int, term_id: int, status: str) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            "UPDATE folder_terms SET status=? WHERE folder_id=? AND term_id=?",
            (status, folder_id, term_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ----- audit log -----
def log_edit(
    conn: sqlite3.Connection,
    actor: str,
    entity: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    ts: str,
) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            (
                "INSERT INTO edit_log(actor, entity, entity_id, action, before, after, ts) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                actor,
                entity,
                entity_id,
                action,
                None if before is None else json.dumps(before, ensure_ascii=False),
                None if after is None else json.dumps(after, ensure_ascii=False),
                ts,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ----- documents helpers -----
def list_documents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT id, folder_id, filename, sha256, pages FROM documents ORDER BY id ASC")
    return [dict(r) for r in cur.fetchall()]


def get_document_by_id(conn: sqlite3.Connection, document_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, folder_id, filename, sha256, pages FROM documents WHERE id=?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def has_doc_terms(conn: sqlite3.Connection, document_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM doc_terms WHERE document_id=? LIMIT 1", (document_id,)).fetchone()
    return bool(row)


def clear_doc_terms(conn: sqlite3.Connection, document_id: int) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM doc_terms WHERE document_id=?", (document_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_folder_id_for_document(conn: sqlite3.Connection, document_id: int) -> int:
    row = conn.execute("SELECT folder_id FROM documents WHERE id=?", (document_id,)).fetchone()
    return int(row[0]) if row else -1


def get_documents_by_folder(conn: sqlite3.Connection, folder_id: int) -> list[int]:
    cur = conn.execute("SELECT id FROM documents WHERE folder_id=? ORDER BY id ASC", (folder_id,))
    return [int(r[0]) for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# YAML → DB ingestion (idempotente)
# ─────────────────────────────────────────────────────────────────────────────

_VALID_ROOTS = ("raw/", "book/", "semantic/")


def _norm_term(value: Any) -> str:
    try:
        normalized = str(value).strip().lower()
    except Exception:
        return ""
    return normalized


def _norm_path(value: Any) -> str:
    """
    Normalizza percorsi di cartella:
      - converte in stringa POSIX, rimuove backslash
      - vieta assoluti e traversal
      - garantisce prefissi noti (raw/, book/, semantic/)
    """
    try:
        path_str = str(value).strip().replace("\\", "/")
    except Exception:
        return ""
    if not path_str:
        return ""

    while path_str.startswith("./"):
        path_str = path_str[2:]

    if path_str.startswith("/") or ".." in path_str.split("/"):
        raise ConfigError(f"Percorso non valido nel YAML: {value}")

    if not any(path_str.startswith(root) for root in _VALID_ROOTS):
        path_str = "raw/" + path_str.lstrip("/")

    while "//" in path_str:
        path_str = path_str.replace("//", "/")

    return path_str.rstrip("/")


def _parent_of(path_str: str) -> str | None:
    if "/" not in path_str:
        return None
    parent = path_str.rsplit("/", 1)[0]
    return parent or None


@dataclass(frozen=True)
class _TagMutation:
    canonical: str
    aliases: list[str]
    folders: list[tuple[str, float, str]]


def parse_yaml_safe(yaml_path: str | Path) -> tuple[Path, Path, list[Any]]:
    ypath = Path(yaml_path)
    raise ConfigError(
        "Import YAML legacy non supportato: usa semantic/tags.db come SSoT.",
        file_path=str(ypath),
    )


def build_mutations(items: list[Any]) -> tuple[list[_TagMutation], int]:
    mutations: list[_TagMutation] = []
    skipped = 0

    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue

        canonical = _norm_term(item.get("canonical") or item.get("name"))
        if not canonical:
            skipped += 1
            continue

        raw_aliases = item.get("aliases") or item.get("synonyms") or []
        aliases: list[str] = []
        if isinstance(raw_aliases, (list, tuple)):
            for alias_value in raw_aliases:
                alias = _norm_term(alias_value)
                if not alias or alias == canonical:
                    continue
                if alias not in aliases:
                    aliases.append(alias)

        raw_folders = item.get("folders") or []
        if not isinstance(raw_folders, (list, tuple)):
            skipped += 1
            continue

        folder_entries: list[tuple[str, float, str]] = []
        for entry in raw_folders:
            try:
                if isinstance(entry, dict):
                    raw_path = entry.get("path")
                    weight = float(entry.get("weight", 1.0))
                    status = str(entry.get("status", "keep"))
                else:
                    raw_path = entry
                    weight = 1.0
                    status = "keep"
                path = _norm_path(raw_path)
            except ConfigError:
                raise
            except Exception:
                skipped += 1
                continue
            folder_entries.append((path, weight, status))

        mutations.append(_TagMutation(canonical=canonical, aliases=aliases, folders=folder_entries))

    return mutations, skipped


def persist_with_transaction(
    conn: Any,
    mutations: list[_TagMutation],
    *,
    default_lang: str,
) -> dict[str, int]:
    counts = {"terms": 0, "aliases": 0, "folders": 0, "links": 0, "skipped": 0}
    seen_terms: set[str] = set()
    seen_aliases: set[tuple[str, str]] = set()
    seen_folders: set[str] = set()
    seen_links: set[tuple[str, str]] = set()

    for mutation in mutations:
        canonical = mutation.canonical

        try:
            term_id = upsert_term(conn, canonical, default_lang)
        except Exception as exc:  # pragma: no cover
            raise ConfigError(f"Impossibile registrare il termine '{canonical}'.") from exc

        if canonical not in seen_terms:
            counts["terms"] += 1
            seen_terms.add(canonical)

        for alias in mutation.aliases:
            key = (canonical, alias)
            if key in seen_aliases:
                continue
            add_term_alias(conn, term_id, alias)
            seen_aliases.add(key)
            counts["aliases"] += 1

        if not mutation.folders:
            continue

        for path, weight, status in mutation.folders:
            parent = _parent_of(path)
            try:
                folder_id = upsert_folder(conn, path, parent_path=parent)
            except Exception as exc:  # pragma: no cover
                raise ConfigError(f"Impossibile registrare la cartella '{path}'.") from exc

            if path not in seen_folders:
                counts["folders"] += 1
                seen_folders.add(path)

            link_key = (canonical, path)
            if link_key in seen_links:
                continue
            try:
                upsert_folder_term(conn, folder_id, term_id, weight=float(weight), status=str(status))
            except Exception as exc:  # pragma: no cover
                raise ConfigError(f"Impossibile associare '{canonical}' a '{path}'.") from exc
            counts["links"] += 1
            seen_links.add(link_key)

    return counts


def import_tags_yaml_to_db(
    yaml_path: str | Path,
    *,
    logger: Any | None = None,
    default_lang: str = "it",
) -> dict[str, int]:
    """Import YAML legacy non supportato: usare semantic/tags.db come SSoT."""
    _ = logger, default_lang
    raise ConfigError(
        "Import YAML non supportato: rigenera semantic/tags.db prima di procedere.",
        file_path=str(Path(yaml_path)),
    )


if __name__ == "__main__":  # pragma: no cover
    path = "output/dev/semantic/tags.db"
    ensure_schema_v2(path)
    with get_conn(path) as conn:
        f = upsert_folder(conn, "raw/marketing")
        d = upsert_document(conn, f, "brochure.pdf", None, 12)
        t = upsert_term(conn, "brand identity")
        add_term_alias(conn, t, "identita' di marca")
        save_doc_terms(conn, d, [("brand identity", 0.86, "yake")])
        upsert_folder_term(conn, f, t, 1.23, "keep", None)
        terms = get_folder_terms(conn, f, "keep", 10)
        LOG.info(
            "storage.tags_store.sample_terms",
            extra={"folder": "raw/marketing", "terms": str(terms)[:300]},
        )
