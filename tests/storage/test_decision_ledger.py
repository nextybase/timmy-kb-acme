# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger


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
    (root / "config" / "config.yaml").write_text('meta:\n  client_name: "Acme"\n', encoding="utf-8")
    return root


def test_decision_ledger_schema_and_inserts(tmp_path: Path) -> None:
    workspace_root = _prepare_workspace(tmp_path / "acme")
    layout = WorkspaceLayout.from_workspace(workspace_root, slug="acme")
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-1",
            slug="acme",
            started_at="2026-01-01T00:00:00Z",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-1",
            run_id="run-1",
            slug="acme",
            gate_name="evidence",
            from_state="WORKSPACE_BOOTSTRAP",
            to_state="SEMANTIC_INGEST",
            verdict=decision_ledger.DECISION_ALLOW,
            subject="workspace",
            decided_at="2026-01-01T00:00:01Z",
            evidence_json="{}",
            rationale="ok",
        )
        run_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        decision_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    finally:
        conn.close()
    assert run_count == 1
    assert decision_count == 1


def test_normative_decision_record_maps_allow(tmp_path: Path) -> None:
    workspace_root = _prepare_workspace(tmp_path / "acme")
    layout = WorkspaceLayout.from_workspace(workspace_root, slug="acme")
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-2",
            slug="acme",
            started_at="2026-01-02T00:00:00Z",
        )
        record = decision_ledger.NormativeDecisionRecord(
            decision_id="dec-2",
            run_id="run-2",
            slug="acme",
            gate_name="evidence",
            from_state="WORKSPACE_BOOTSTRAP",
            to_state="SEMANTIC_INGEST",
            verdict=decision_ledger.NORMATIVE_PASS,
            subject="workspace",
            decided_at="2026-01-02T00:00:01Z",
            actor="gatekeeper:evidence",
            evidence_refs=["log:ctx"],
        )
        decision_ledger.record_normative_decision(conn, record)
        row = conn.execute(
            "SELECT verdict, evidence_json, rationale FROM decisions WHERE decision_id = ?",
            ("dec-2",),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == decision_ledger.DECISION_ALLOW
    evidence = json.loads(row[1])
    assert evidence["actor"] == "gatekeeper:evidence"
    assert evidence["evidence_refs"] == ["log:ctx"]
    assert evidence["conditions"] == []
    assert evidence["normative_verdict"] == decision_ledger.NORMATIVE_PASS
    assert "normative_verdict=PASS" in row[2]


def test_normative_decision_record_requires_to_state(tmp_path: Path) -> None:
    workspace_root = _prepare_workspace(tmp_path / "acme")
    layout = WorkspaceLayout.from_workspace(workspace_root, slug="acme")
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-3",
            slug="acme",
            started_at="2026-01-03T00:00:00Z",
        )
        record = decision_ledger.NormativeDecisionRecord(
            decision_id="dec-3",
            run_id="run-3",
            slug="acme",
            gate_name="evidence",
            from_state="WORKSPACE_BOOTSTRAP",
            to_state=None,
            verdict=decision_ledger.NORMATIVE_PASS,
            subject="workspace",
            decided_at="2026-01-03T00:00:01Z",
            actor="gatekeeper:evidence",
        )
        with pytest.raises(ValueError, match="to_state"):
            decision_ledger.record_normative_decision(conn, record)
    finally:
        conn.close()


def test_normative_decision_record_requires_stop_code(tmp_path: Path) -> None:
    workspace_root = _prepare_workspace(tmp_path / "acme")
    layout = WorkspaceLayout.from_workspace(workspace_root, slug="acme")
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-4",
            slug="acme",
            started_at="2026-01-04T00:00:00Z",
        )
        record = decision_ledger.NormativeDecisionRecord(
            decision_id="dec-4",
            run_id="run-4",
            slug="acme",
            gate_name="skeptic",
            from_state="SEMANTIC_INGEST",
            to_state="FRONTMATTER_ENRICH",
            verdict=decision_ledger.NORMATIVE_BLOCK,
            subject="workspace",
            decided_at="2026-01-04T00:00:01Z",
            actor="gatekeeper:skeptic",
        )
        with pytest.raises(ValueError, match="stop_code"):
            decision_ledger.record_normative_decision(conn, record)
    finally:
        conn.close()
