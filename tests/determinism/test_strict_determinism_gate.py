# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger
from tests._helpers.workspace_paths import local_workspace_dir

PY = sys.executable


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
    # Due PDF deterministici per mantenere un layout realistico del workspace.
    (root / "raw" / "doc-a.pdf").write_bytes(b"%PDF-1.4\nA\n")
    (root / "raw" / "doc-b.pdf").write_bytes(b"%PDF-1.4\nB\n")
    return root


def _seed_deterministic_ledger(*, workspace_root: Path, slug: str) -> None:
    layout = WorkspaceLayout.from_workspace(workspace_root, slug=slug)
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.start_run(
            conn,
            run_id="run-det-001",
            slug=slug,
            started_at="2026-01-01T00:00:00Z",
        )
        decision_ledger.record_decision(
            conn,
            decision_id="dec-det-001",
            run_id="run-det-001",
            slug=slug,
            gate_name="pre_onboarding",
            from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
            to_state=decision_ledger.STATE_SEMANTIC_INGEST,
            verdict=decision_ledger.DECISION_ALLOW,
            subject="pre_onboarding",
            decided_at="2026-01-01T00:00:01Z",
            evidence_json='{"dummy_mode":false}',
            rationale="ok",
        )
    finally:
        conn.close()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_core_artifacts(workspace_root: Path) -> dict[str, str]:
    allowlist = [
        workspace_root / "config" / "config.yaml",
        workspace_root / "config" / "ledger.db",
        workspace_root / "book" / "README.md",
        workspace_root / "book" / "SUMMARY.md",
    ]
    return {p.relative_to(workspace_root).as_posix(): _sha256_file(p) for p in allowlist}


def _run_ledger_status(*, slug: str, workspace_root: Path, repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TIMMY_BETA_STRICT"] = "1"
    env["WORKSPACE_ROOT_DIR"] = str(workspace_root)
    env.pop("REPO_ROOT_DIR", None)
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    return subprocess.run(
        [PY, "-m", "timmy_kb.cli", "ledger-status", "--slug", slug, "--json"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )


def _extract_json_line(stdout_text: str) -> dict[str, object]:
    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    assert lines, "stdout vuoto: payload JSON non trovato"
    return json.loads(lines[-1])


def test_strict_determinism_gate_for_ledger_status(tmp_path: Path) -> None:
    slug = "acme"
    workspace_root = _prepare_workspace(local_workspace_dir(tmp_path, slug))
    _seed_deterministic_ledger(workspace_root=workspace_root, slug=slug)

    repo_root = Path(__file__).resolve().parents[2]

    run_a = _run_ledger_status(slug=slug, workspace_root=workspace_root, repo_root=repo_root)
    assert run_a.returncode == 0
    assert run_a.stderr == ""
    payload_a = _extract_json_line(run_a.stdout)
    snapshot_a = _snapshot_core_artifacts(workspace_root)

    run_b = _run_ledger_status(slug=slug, workspace_root=workspace_root, repo_root=repo_root)
    assert run_b.returncode == 0
    assert run_b.stderr == ""
    payload_b = _extract_json_line(run_b.stdout)
    snapshot_b = _snapshot_core_artifacts(workspace_root)

    assert payload_a == payload_b
    assert snapshot_a == snapshot_b
