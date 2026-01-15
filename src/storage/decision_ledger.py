# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Final

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.workspace_layout import WorkspaceLayout

__all__ = [
    "DECISION_ALLOW",
    "DECISION_DENY",
    "ledger_path_from_layout",
    "open_ledger",
    "start_run",
    "record_decision",
]

DECISION_ALLOW: Final[str] = "ALLOW"
DECISION_DENY: Final[str] = "DENY"
_DECISION_VALUES: Final[set[str]] = {DECISION_ALLOW, DECISION_DENY}

_SCHEMA_SQL: Final[
    str
] = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    started_at TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('ALLOW', 'DENY')),
    subject TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    evidence_json TEXT,
    rationale TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
"""


def ledger_path_from_layout(layout: WorkspaceLayout) -> Path:
    config_dir = layout.config_path.parent
    if not config_dir.exists() or not config_dir.is_dir():
        raise ConfigError(
            "Directory config mancante per il ledger",
            slug=layout.slug,
            file_path=config_dir,
        )
    return ensure_within_and_resolve(layout.base_dir, config_dir / "ledger.db")


def open_ledger(layout: WorkspaceLayout) -> sqlite3.Connection:
    db_path = ledger_path_from_layout(layout)
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        raise ConfigError(
            f"Errore apertura ledger: {exc}",
            slug=layout.slug,
            file_path=db_path,
        ) from exc
    _init_schema(conn, slug=layout.slug, db_path=db_path)
    return conn


def start_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    slug: str,
    started_at: str,
    metadata_json: str | None = None,
) -> None:
    _insert_row(
        conn,
        "INSERT INTO runs (run_id, slug, started_at, metadata_json) VALUES (?, ?, ?, ?)",
        (run_id, slug, started_at, metadata_json),
        hint="start_run",
        slug=slug,
    )


def record_decision(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    run_id: str,
    slug: str,
    gate_name: str,
    from_state: str,
    to_state: str,
    verdict: str,
    subject: str,
    decided_at: str,
    evidence_json: str | None = None,
    rationale: str | None = None,
) -> None:
    if verdict not in _DECISION_VALUES:
        raise ValueError(f"Verdetto non valido: {verdict}")
    _insert_row(
        conn,
        "INSERT INTO decisions ("
        "decision_id, run_id, gate_name, from_state, to_state, verdict, subject, decided_at, evidence_json, rationale"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            run_id,
            gate_name,
            from_state,
            to_state,
            verdict,
            subject,
            decided_at,
            evidence_json,
            rationale,
        ),
        hint="record_decision",
        slug=slug,
    )


def _init_schema(conn: sqlite3.Connection, *, slug: str, db_path: Path) -> None:
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA_SQL)
    except sqlite3.Error as exc:
        raise PipelineError(
            f"Errore inizializzazione ledger: {exc}",
            slug=slug,
            file_path=db_path,
        ) from exc


def _insert_row(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
    *,
    hint: str,
    slug: str | None = None,
) -> None:
    db_path = _resolve_db_path(conn)
    try:
        with conn:
            conn.execute(sql, params)
    except sqlite3.Error as exc:
        raise PipelineError(
            f"Errore insert ledger ({hint}): {exc}",
            slug=slug,
            file_path=db_path,
        ) from exc


def _resolve_db_path(conn: sqlite3.Connection) -> Path | None:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return None
    for _, name, file_path in rows:
        if name == "main" and file_path:
            return Path(file_path)
    return None
