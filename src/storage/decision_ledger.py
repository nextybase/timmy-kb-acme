# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.workspace_layout import WorkspaceLayout

__all__ = [
    "DECISION_ALLOW",
    "DECISION_DENY",
    "STATE_WORKSPACE_BOOTSTRAP",
    "STATE_SEMANTIC_INGEST",
    "STATE_FRONTMATTER_ENRICH",
    "STATE_VISUALIZATION_REFRESH",
    "STATE_PREVIEW_READY",
    "NormativeDecisionRecord",
    "ledger_path_from_layout",
    "open_ledger",
    "start_run",
    "record_decision",
    "record_normative_decision",
]

DECISION_ALLOW: Final[str] = "ALLOW"
DECISION_DENY: Final[str] = "DENY"
_DECISION_VALUES: Final[set[str]] = {DECISION_ALLOW, DECISION_DENY}
STATE_WORKSPACE_BOOTSTRAP: Final[str] = "WORKSPACE_BOOTSTRAP"
STATE_SEMANTIC_INGEST: Final[str] = "SEMANTIC_INGEST"
STATE_FRONTMATTER_ENRICH: Final[str] = "FRONTMATTER_ENRICH"
STATE_VISUALIZATION_REFRESH: Final[str] = "VISUALIZATION_REFRESH"
STATE_PREVIEW_READY: Final[str] = "PREVIEW_READY"
_CANONICAL_STATE_ORDER: Final[tuple[str, ...]] = (
    STATE_WORKSPACE_BOOTSTRAP,
    STATE_SEMANTIC_INGEST,
    STATE_FRONTMATTER_ENRICH,
    STATE_VISUALIZATION_REFRESH,
    STATE_PREVIEW_READY,
)
_CANONICAL_STATES: Final[set[str]] = set(_CANONICAL_STATE_ORDER)
NORMATIVE_PASS: Final[str] = "PASS"
NORMATIVE_PASS_WITH_CONDITIONS: Final[str] = "PASS_WITH_CONDITIONS"
NORMATIVE_BLOCK: Final[str] = "BLOCK"
NORMATIVE_FAIL: Final[str] = "FAIL"
_NORMATIVE_ALLOW: Final[set[str]] = {NORMATIVE_PASS, NORMATIVE_PASS_WITH_CONDITIONS}
_NORMATIVE_DENY: Final[set[str]] = {NORMATIVE_BLOCK, NORMATIVE_FAIL}

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


@dataclass(frozen=True)
class NormativeDecisionRecord:
    decision_id: str
    run_id: str
    slug: str
    gate_name: str
    from_state: str
    to_state: str | None
    verdict: str
    subject: str
    decided_at: str
    actor: str
    evidence_refs: list[str] | None = None
    stop_code: str | None = None
    conditions: list[str] | None = None
    rationale: str | None = None


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
    _validate_state(from_state, field_name="from_state")
    _validate_state(to_state, field_name="to_state")
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


def _validate_state(value: str, *, field_name: str) -> None:
    if value not in _CANONICAL_STATES:
        raise ConfigError(
            f"State '{value}' non canonico per ledger ({field_name}).",
            file_path=None,
        )


def record_normative_decision(conn: sqlite3.Connection, record: NormativeDecisionRecord) -> None:
    ledger_verdict = _map_normative_verdict(record.verdict)
    if not record.to_state:
        raise ValueError("to_state richiesto per la persistenza nel ledger")
    if not record.actor:
        raise ValueError("actor richiesto per il Decision Record normativo")
    if record.verdict in _NORMATIVE_DENY and not record.stop_code:
        raise ValueError("stop_code richiesto per BLOCK/FAIL")
    conditions = _normalize_str_list(record.conditions, field_name="conditions")
    if record.verdict == NORMATIVE_PASS_WITH_CONDITIONS and not conditions:
        raise ValueError("conditions richieste per PASS_WITH_CONDITIONS")
    evidence_refs = _normalize_str_list(record.evidence_refs, field_name="evidence_refs")
    evidence_payload = {
        "actor": record.actor,
        "conditions": conditions,
        "evidence_refs": evidence_refs,
        "normative_verdict": record.verdict,
    }
    if record.stop_code:
        evidence_payload["stop_code"] = record.stop_code
    evidence_json = json.dumps(evidence_payload, sort_keys=True)
    rationale = _build_rationale(record, conditions)
    record_decision(
        conn,
        decision_id=record.decision_id,
        run_id=record.run_id,
        slug=record.slug,
        gate_name=record.gate_name,
        from_state=record.from_state,
        to_state=record.to_state,
        verdict=ledger_verdict,
        subject=record.subject,
        decided_at=record.decided_at,
        evidence_json=evidence_json,
        rationale=rationale,
    )


def _map_normative_verdict(verdict: str) -> str:
    if verdict in _NORMATIVE_ALLOW:
        return DECISION_ALLOW
    if verdict in _NORMATIVE_DENY:
        return DECISION_DENY
    raise ValueError(f"Verdetto normativo non valido: {verdict}")


def _normalize_str_list(value: list[str] | None, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{field_name} deve essere una lista di stringhe")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} deve contenere solo stringhe")
    return value


def _build_rationale(record: NormativeDecisionRecord, conditions: list[str]) -> str:
    parts = [f"normative_verdict={record.verdict}", f"actor={record.actor}"]
    if record.stop_code:
        parts.append(f"stop_code={record.stop_code}")
    if conditions:
        parts.append("conditions=" + ",".join(conditions))
    if record.rationale:
        parts.append(f"note={record.rationale}")
    return "; ".join(parts)


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
