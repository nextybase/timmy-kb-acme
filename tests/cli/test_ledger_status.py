# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pipeline.workspace_layout import WorkspaceLayout
from tests._helpers.workspace_paths import local_workspace_dir
from storage import decision_ledger
from timmy_kb.cli import ledger_status


def _prepare_workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir()
    (root / "normalized").mkdir()
    (root / "book").mkdir()
    (root / "semantic").mkdir()
    (root / "logs").mkdir()
    (root / "config").mkdir()
    (root / "book" / "README.md").write_text("# README\n", encoding="utf-8")
    (root / "book" / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (root / "config" / "config.yaml").write_text(
        'meta:\n  client_name: "Acme"\nops:\n  log_level: "INFO"\n',
        encoding="utf-8",
    )
    return root


def test_ledger_status_anchored_to_latest_run(tmp_path: Path, monkeypatch, capsys) -> None:
    slug = "acme"
    workspace_root = _prepare_workspace(local_workspace_dir(tmp_path, slug))
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(workspace_root))

    layout = WorkspaceLayout.from_workspace(workspace_root, slug=slug)
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-a",
            slug=slug,
            started_at="2026-01-01T00:00:00Z",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-a-1",
            run_id="run-a",
            slug=slug,
            gate_name="semantic_onboarding",
            from_state=decision_ledger.STATE_SEMANTIC_INGEST,
            to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
            verdict=decision_ledger.DECISION_ALLOW,
            subject="semantic_onboarding",
            decided_at="2026-01-01T00:00:01Z",
            evidence_json="{}",
            rationale="ok",
        )
        decision_ledger.start_run(
            conn,
            run_id="run-b",
            slug=slug,
            started_at="2026-01-02T00:00:00Z",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-b-1",
            run_id="run-b",
            slug=slug,
            gate_name="pre_onboarding",
            from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
            to_state=decision_ledger.STATE_SEMANTIC_INGEST,
            verdict=decision_ledger.DECISION_ALLOW,
            subject="pre_onboarding",
            decided_at="2026-01-02T00:00:01Z",
            evidence_json="{}",
            rationale="ok",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-b-2",
            run_id="run-b",
            slug=slug,
            gate_name="tag_onboarding",
            from_state=decision_ledger.STATE_SEMANTIC_INGEST,
            to_state=decision_ledger.STATE_SEMANTIC_INGEST,
            verdict=decision_ledger.DECISION_ALLOW,
            subject="tag_onboarding",
            decided_at="2026-01-02T00:00:02Z",
            evidence_json="{}",
            rationale="ok",
        )
    finally:
        conn.close()

    rc = ledger_status.run(slug=slug, json_output=True)
    assert rc == 0

    out = capsys.readouterr().out.strip()
    assert out
    lines = [line for line in out.splitlines() if line.strip()]
    json_line = lines[-1]
    assert "\n" not in json_line
    status = json.loads(json_line)

    assert status["latest_run"]["run_id"] == "run-b"
    assert status["current_state"] == decision_ledger.STATE_SEMANTIC_INGEST

    gate_names = [gate["gate_name"] for gate in status["gates"]]
    assert gate_names == sorted(gate_names)
    assert gate_names == ["pre_onboarding", "tag_onboarding"]


def test_ledger_status_fails_fast_on_old_sqlite(tmp_path: Path, monkeypatch) -> None:
    slug = "acme"
    workspace_root = _prepare_workspace(local_workspace_dir(tmp_path, slug))
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(workspace_root))

    layout = WorkspaceLayout.from_workspace(workspace_root, slug=slug)
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-old",
            slug=slug,
            started_at="2026-01-01T00:00:00Z",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-old-1",
            run_id="run-old",
            slug=slug,
            gate_name="tag_onboarding",
            from_state=decision_ledger.STATE_SEMANTIC_INGEST,
            to_state=decision_ledger.STATE_SEMANTIC_INGEST,
            verdict=decision_ledger.DECISION_ALLOW,
            subject="tag_onboarding",
            decided_at="2026-01-01T00:00:01Z",
            evidence_json="{}",
            rationale="ok",
        )
    finally:
        conn.close()

    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 24, 0))
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.24.0")

    rc = ledger_status.run(slug=slug, json_output=True)
    assert rc != 0
