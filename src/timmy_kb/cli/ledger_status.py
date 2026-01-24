#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ledger status (read-only)")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--json", action="store_true", help="Output JSON deterministico")
    return p.parse_args()


def _open_readonly(db_path: Path, *, slug: str) -> sqlite3.Connection:
    if not db_path.exists() or not db_path.is_file():
        raise ConfigError("Ledger mancante", slug=slug, file_path=db_path)
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ConfigError("Errore apertura ledger.", slug=slug, file_path=db_path) from exc


def _load_latest_run(conn: sqlite3.Connection) -> dict[str, str] | None:
    row = conn.execute("SELECT run_id, started_at FROM runs ORDER BY started_at DESC, run_id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {"run_id": str(row[0]), "started_at": str(row[1])}


def _load_latest_decisions(conn: sqlite3.Connection, *, run_id: str) -> list[dict[str, Any]]:
    if sqlite3.sqlite_version_info < (3, 25, 0):
        raise ConfigError(
            "ledger-status richiede window functions: " f"versione={sqlite3.sqlite_version} minima=3.25.0 richiesta",
        )
    rows = conn.execute(
        """
        SELECT gate_name, verdict, from_state, to_state, decided_at, subject, evidence_json, decision_id
        FROM (
            SELECT
                gate_name,
                verdict,
                from_state,
                to_state,
                decided_at,
                subject,
                evidence_json,
                decision_id,
                ROW_NUMBER() OVER (
                    PARTITION BY gate_name
                    ORDER BY decided_at DESC, decision_id DESC
                ) AS rn
            FROM decisions
            WHERE run_id = ?
        )
        WHERE rn = 1
        ORDER BY gate_name ASC
        """,
        (run_id,),
    ).fetchall()
    return [
        {
            "gate_name": str(row[0]),
            "verdict": str(row[1]),
            "from_state": str(row[2]),
            "to_state": str(row[3]),
            "decided_at": str(row[4]),
            "subject": str(row[5]),
            "evidence_json": row[6],
        }
        for row in rows
    ]


def _load_current_state(conn: sqlite3.Connection, *, run_id: str) -> str:
    row = conn.execute(
        """
        SELECT to_state
        FROM decisions
        WHERE run_id = ?
          AND verdict = ?
        ORDER BY decided_at DESC, decision_id DESC
        LIMIT 1
        """,
        (run_id, decision_ledger.DECISION_ALLOW),
    ).fetchone()
    if row is None or row[0] is None:
        return "UNKNOWN"
    return str(row[0])


def _parse_evidence(evidence_json: str | None) -> dict[str, Any]:
    if not evidence_json:
        return {}
    try:
        payload = json.loads(evidence_json)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_dummy_mode(evidence: dict[str, Any]) -> bool | None:
    if "dummy_mode" not in evidence:
        return None
    value = evidence.get("dummy_mode")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return None


def _format_dummy_mode(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "true" if value else "false"


def _render_human(status: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"Ledger status for slug: {status['slug']}")
    latest_run = status.get("latest_run")
    if latest_run:
        lines.append(f"Latest run: {latest_run['run_id']} started_at={latest_run['started_at']}")
    else:
        lines.append("Latest run: none")
    lines.append(f"Current state: {status['current_state']}")
    gates: list[dict[str, Any]] = status.get("gates", [])
    if not gates:
        lines.append("Gates: none")
        return "\n".join(lines) + "\n"
    lines.append("Gates:")
    for gate in gates:
        lines.append(f"- {gate['gate_name']}")
        lines.append(f"  verdict: {gate['verdict']}")
        lines.append(f"  from_state: {gate['from_state']}")
        lines.append(f"  to_state: {gate['to_state']}")
        lines.append(f"  decided_at: {gate['decided_at']}")
        lines.append(f"  subject: {gate['subject']}")
        lines.append(f"  dummy_mode: {gate['dummy_mode']}")
        if gate.get("config_path"):
            lines.append(f"  config_path: {gate['config_path']}")
        if gate.get("workspace_root"):
            lines.append(f"  workspace_root: {gate['workspace_root']}")
    return "\n".join(lines) + "\n"


def _collect_status(slug: str) -> dict[str, Any]:
    layout = WorkspaceLayout.from_slug(slug=slug, require_env=False)
    db_path = decision_ledger.ledger_path_from_layout(layout)
    conn = _open_readonly(db_path, slug=slug)
    conn.row_factory = sqlite3.Row
    try:
        latest_run = _load_latest_run(conn)
        if latest_run is None:
            return {"slug": slug, "latest_run": None, "current_state": "UNKNOWN", "gates": []}
        run_id = str(latest_run["run_id"])
        current_state = _load_current_state(conn, run_id=run_id)
        decisions = _load_latest_decisions(conn, run_id=run_id)
    except sqlite3.Error as exc:
        raise PipelineError(f"Errore lettura ledger: {exc}", slug=slug, file_path=db_path) from exc
    finally:
        conn.close()

    gates: list[dict[str, Any]] = []
    for decision in decisions:
        evidence = _parse_evidence(decision.get("evidence_json"))
        dummy_mode = _extract_dummy_mode(evidence)
        gate_entry = {
            "gate_name": decision["gate_name"],
            "verdict": decision["verdict"],
            "from_state": decision["from_state"],
            "to_state": decision["to_state"],
            "decided_at": decision["decided_at"],
            "subject": decision["subject"],
            "dummy_mode": _format_dummy_mode(dummy_mode),
        }
        config_path = evidence.get("config_path")
        workspace_root = evidence.get("workspace_root")
        if isinstance(config_path, str):
            gate_entry["config_path"] = config_path
        if isinstance(workspace_root, str):
            gate_entry["workspace_root"] = workspace_root
        gates.append(gate_entry)

    return {
        "slug": slug,
        "latest_run": latest_run,
        "current_state": current_state,
        "gates": gates,
    }


def run(*, slug: str, json_output: bool) -> int:
    slug = slug.strip()
    if not slug:
        raise ConfigError("Slug vuoto non valido per ledger_status.")
    try:
        status = _collect_status(slug)
    except (ConfigError, PipelineError) as exc:
        return int(exit_code_for(exc))
    except Exception:
        return 99

    if json_output:
        payload = json.dumps(status, sort_keys=True, separators=(",", ":"))
        sys.stdout.write(payload + "\n")
        return 0

    sys.stdout.write(_render_human(status))
    return 0


def main() -> int:
    args = _parse_args()
    return run(slug=args.slug, json_output=bool(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
