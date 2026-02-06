# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.qa_evidence import write_qa_evidence
from pipeline.qa_gate import QaGateViolation
from storage import decision_ledger
from tests._helpers.workspace_paths import local_workspace_dir
from tests.utils.workspace import ensure_minimal_workspace_layout
from timmy_kb.cli import semantic_onboarding as mod


def _create_layout(tmp_path: Path) -> Path:
    base = local_workspace_dir(tmp_path / "output", "dummy")
    ensure_minimal_workspace_layout(base, client_name="dummy")
    return base


def _start_run(conn, slug: str, run_id: str) -> None:
    decision_ledger.start_run(
        conn,
        run_id=run_id,
        slug=slug,
        started_at=_current_timestamp(),
    )


def _current_run_id() -> str:
    return uuid.uuid4().hex


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_qa_gate_records_pass(tmp_path: Path) -> None:
    base = _create_layout(tmp_path)
    layout = mod.WorkspaceLayout.from_workspace(base, slug="dummy")
    write_qa_evidence(
        layout.logs_dir,
        checks_executed=["pre-commit run --all-files", "pytest -q"],
        qa_status="pass",
    )
    conn = decision_ledger.open_ledger(layout)
    run_id = _current_run_id()
    _start_run(conn, slug="dummy", run_id=run_id)
    mod._run_qa_gate_and_record(conn, layout=layout, slug="dummy", run_id=run_id)
    rows = conn.execute(
        "SELECT gate_name, verdict FROM decisions WHERE gate_name = ?",
        ("qa_gate",),
    ).fetchall()
    assert rows, "qa_gate decision should be recorded"
    assert len(rows) == 1
    assert rows[0][1] == decision_ledger.DECISION_ALLOW
    conn.close()


def test_qa_gate_failure_records_block_only(tmp_path: Path) -> None:
    base = _create_layout(tmp_path)
    layout = mod.WorkspaceLayout.from_workspace(base, slug="dummy")
    conn = decision_ledger.open_ledger(layout)
    run_id = _current_run_id()
    _start_run(conn, slug="dummy", run_id=run_id)
    with pytest.raises(QaGateViolation):
        mod._run_qa_gate_and_record(conn, layout=layout, slug="dummy", run_id=run_id)
    qa_rows = conn.execute(
        "SELECT gate_name, verdict FROM decisions WHERE gate_name = ?",
        ("qa_gate",),
    ).fetchall()
    assert qa_rows and len(qa_rows) == 1
    assert qa_rows[0][1] == decision_ledger.DECISION_DENY
    semantic_rows = conn.execute(
        "SELECT gate_name FROM decisions WHERE gate_name = ?",
        ("semantic_onboarding",),
    ).fetchall()
    assert not semantic_rows, "semantic_onboarding should not be recorded on QA failure"
    conn.close()
