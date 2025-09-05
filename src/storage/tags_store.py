from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
import json

__all__ = [
    "load_tags_reviewed",
    "save_tags_reviewed",
    "derive_db_path_from_yaml_path",
    "ensure_schema_v2",
    "migrate_to_v2",
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


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(
        """
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
        """
    )


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
    """Dato il path YAML (es. semantic/tags_reviewed.yaml), ritorna il path DB adiacente 'tags.db'."""
    pp = Path(p)
    return str(pp.parent / "tags.db")


def load_tags_reviewed(db_path: str) -> Dict[str, Any]:
    """Ritorna un dict con la stessa struttura del file YAML legacy.

    Struttura:
    {
      "version": str,
      "reviewed_at": str,
      "keep_only_listed": bool,
      "tags": [ {"name": str, "action": str, "synonyms": [str,...], "note": str|None}, ... ]
    }
    Se il DB è assente o vuoto, ritorna la struttura minima di default.
    """
    dbp = Path(db_path)
    if not dbp.parent.exists():
        dbp.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(dbp)
    try:
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
        tags: List[Dict[str, Any]] = []
        cur = conn.execute(
            "SELECT id, name, action, note FROM tags ORDER BY name COLLATE NOCASE ASC"
        )
        tag_rows = cur.fetchall()
        for tid, name, action, note in tag_rows:
            scur = conn.execute(
                "SELECT alias FROM tag_synonyms WHERE tag_id=? ORDER BY pos ASC, alias COLLATE NOCASE ASC",
                (tid,),
            )
            syns = [str(r[0]) for r in scur.fetchall()]
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
    finally:
        conn.close()


def save_tags_reviewed(db_path: str, data: Dict[str, Any]) -> None:
    """Persiste in SQLite (upsert) lo stesso dict precedentemente scritto in YAML."""
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
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

        # Rebuild tags and synonyms from incoming data (idempotent and simple)
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
            note = item.get("note")
            note_val = None if note is None else str(note)
            cur = conn.execute(
                "INSERT INTO tags(name, action, note) VALUES(?, ?, ?)", (name, action, note_val)
            )
            tid = cur.lastrowid
            syns = item.get("synonyms") or []
            try:
                for pos, alias in enumerate([str(s) for s in syns if str(s).strip()], start=0):
                    conn.execute(
                        "INSERT OR IGNORE INTO tag_synonyms(tag_id, alias, pos) VALUES(?, ?, ?)",
                        (tid, alias, pos),
                    )
            except TypeError:
                # non-iterable synonyms; ignore
                pass

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------
# v2 Schema management/migration
# ------------------------------

_V2_TABLES = [
    "folders",
    "documents",
    "terms",
    "term_aliases",
    "doc_terms",
    "folder_terms",
    "edit_log",
]


def _create_v2_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(
        """
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
        """
    )


def ensure_schema_v2(db_path: str) -> None:
    """Ensure the DB has v1 base schema and all v2 tables and indexes.

    Does not alter meta.version. Use migrate_to_v2() for migration semantics.
    """
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    try:
        conn.execute("BEGIN")
        _ensure_schema(conn)
        _create_v2_tables(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_to_v2(db_path: str) -> None:
    """Create v2 tables if missing and set meta.version='2' only if any table was created.

    load/save semantics remain unchanged; this only manages structure and meta version.
    """
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    try:
        _ensure_schema(conn)
        # Detect missing tables
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (%s)"
            % (",".join(["?"] * len(_V2_TABLES))),
            _V2_TABLES,
        )
        present = {r[0] for r in cur.fetchall()}
        missing = [t for t in _V2_TABLES if t not in present]

        conn.execute("BEGIN")
        _create_v2_tables(conn)

        if missing:
            # Upsert meta to version '2' (preserve other fields where possible)
            cur = conn.execute("SELECT version, reviewed_at, keep_only_listed FROM meta WHERE id=1")
            row = cur.fetchone()
            if row is None:
                version = "2"
                reviewed_at = _now_iso()
                keep_only_listed = 0
            else:
                # keep existing reviewed_at/keep_only_listed
                version = "2"
                reviewed_at = str(row[1])
                keep_only_listed = _to_int(row[2])
            conn.execute(
                "INSERT INTO meta(id, version, reviewed_at, keep_only_listed) VALUES(1, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET version=excluded.version",
                (version, reviewed_at, keep_only_listed),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ------------------------------
# v2 CRUD helpers (no pipeline usage yet)
# ------------------------------


def get_conn(db_path: str) -> sqlite3.Connection:
    """Ritorna una connessione con row_factory=sqlite3.Row e FK abilitate."""
    dbp = Path(db_path)
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ----- folders/documents -----
def upsert_folder(conn: sqlite3.Connection, path: str, parent_path: str | None = None) -> int:
    parent_id = None
    if parent_path:
        # Crea/recupera il parent ricorsivamente
        row = conn.execute("SELECT id FROM folders WHERE path=?", (parent_path,)).fetchone()
        if row is None:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    "INSERT INTO folders(path, parent_id) VALUES(?, NULL) ON CONFLICT(path) DO NOTHING",
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
            "INSERT INTO documents(folder_id, filename, sha256, pages) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(folder_id, filename) DO UPDATE SET sha256=excluded.sha256, pages=excluded.pages",
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


def get_folder_by_path(conn: sqlite3.Connection, path: str) -> dict | None:
    row = conn.execute("SELECT id, path, parent_id FROM folders WHERE path=?", (path,)).fetchone()
    return dict(row) if row else None


def list_folders(conn: sqlite3.Connection) -> list[dict]:
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


def get_term_by_canonical(
    conn: sqlite3.Connection, canonical: str, lang: str = "it"
) -> dict | None:
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
def save_doc_terms(
    conn: sqlite3.Connection, document_id: int, items: list[tuple[str, float, str]]
) -> None:
    """items = [(phrase, score, method)] → upsert su doc_terms"""
    conn.execute("BEGIN")
    try:
        for phrase, score, method in items or []:
            conn.execute(
                "INSERT INTO doc_terms(document_id, phrase, score, method) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(document_id, phrase) DO UPDATE SET score=excluded.score, method=excluded.method",
                (document_id, phrase, float(score), method),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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


def set_folder_term_status(
    conn: sqlite3.Connection, folder_id: int, term_id: int, status: str
) -> None:
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
    before: dict | None,
    after: dict | None,
    ts: str,
) -> None:
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO edit_log(actor, entity, entity_id, action, before, after, ts) VALUES(?, ?, ?, ?, ?, ?, ?)",
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
def list_documents(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT id, folder_id, filename, sha256, pages FROM documents ORDER BY id ASC"
    )
    return [dict(r) for r in cur.fetchall()]


def get_document_by_id(conn: sqlite3.Connection, document_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, folder_id, filename, sha256, pages FROM documents WHERE id=?",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def has_doc_terms(conn: sqlite3.Connection, document_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM doc_terms WHERE document_id=? LIMIT 1", (document_id,)
    ).fetchone()
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


if __name__ == "__main__":  # pragma: no cover

    path = "output/dev/semantic/tags.db"
    ensure_schema_v2(path)
    conn = get_conn(path)
    f = upsert_folder(conn, "raw/marketing")
    d = upsert_document(conn, f, "brochure.pdf", None, 12)
    t = upsert_term(conn, "brand identity")
    add_term_alias(conn, t, "identità di marca")
    save_doc_terms(conn, d, [("brand identity", 0.86, "yake")])
    upsert_folder_term(conn, f, t, 1.23, "keep", None)
    print(get_folder_terms(conn, f, "keep", 10))
