# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from pipeline.context import ClientContext
from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME, write_qa_evidence
from pipeline.workspace_bootstrap import bootstrap_dummy_workspace
from pipeline.workspace_layout import WorkspaceLayout
from tests._helpers.workspace_paths import local_workspace_dir


def _resolve_logs_dir(layout: WorkspaceLayout) -> Path:
    """
    Regression helper: accetta entrambe le varianti (logs_dir/log_dir).
    L'obiettivo e' verificare che la CLI non "rompa" per mismatch naming.
    """
    logs_dir = getattr(layout, "logs_dir", None) or getattr(layout, "log_dir", None)
    assert isinstance(logs_dir, Path), "WorkspaceLayout must expose logs_dir or log_dir"
    return logs_dir


def test_cli_qa_evidence_writes_in_logs_dir(tmp_path: Path, monkeypatch) -> None:
    slug = "acme"

    # 1) Crea un workspace dummy isolato in tmp_path
    monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(tmp_path))
    bootstrap_dummy_workspace(slug=slug)

    # Workspace creato sotto: <tmp>/output/<workspace-name> (vedi tests._helpers.workspace_paths)
    workspace_dir = local_workspace_dir(tmp_path / "output", slug)
    assert workspace_dir.exists()

    # 2) Fai puntare il loader al workspace (senza repo_root/output heuristics)
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(workspace_dir))

    # 3) Costruisci context+layout come fa la CLI
    ctx = ClientContext.load(slug=slug, require_drive_env=False, run_id="test", bootstrap_config=False)
    layout = WorkspaceLayout.from_context(ctx)

    logs_dir = _resolve_logs_dir(layout)
    assert logs_dir.name == "logs"
    assert logs_dir.exists()

    # 4) Scrivi QA evidence e verifica path finale
    write_qa_evidence(
        logs_dir,
        checks_executed=["pytest -q"],
        qa_status="pass",
        logger=None,
    )

    qa_path = logs_dir / QA_EVIDENCE_FILENAME
    assert qa_path.exists()
    txt = qa_path.read_text(encoding="utf-8")
    assert '"qa_status": "pass"' in txt
    assert '"checks_executed"' in txt
