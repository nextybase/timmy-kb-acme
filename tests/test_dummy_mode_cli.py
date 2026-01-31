# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError


def _repo_root() -> Path:
    # tests/ è in repo root
    return Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "timmy_kb.cli.tag_onboarding", *args]
    return subprocess.run(cmd, env=env, text=True, capture_output=True)


def test_cli_rejects_removed_shims() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = ";".join(
        [
            str(_repo_root() / "src"),
            str(_repo_root() / "Lib" / "site-packages"),
        ]
    )
    # argparse deve fallire prima di qualunque logica runtime
    res = _run_cli(["--no-strict"], env)
    assert res.returncode == 2
    assert "unrecognized arguments: --no-strict" in (res.stderr or "")

    res = _run_cli(["--force-dummy"], env)
    assert res.returncode == 2
    assert "unrecognized arguments: --force-dummy" in (res.stderr or "")


def test_dummy_capability_forbidden_is_blocked_and_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Setup workspace dummy (non richiede env Drive)
    slug = f"t-{uuid.uuid4().hex[:8]}"

    # Evitiamo side effect su output/ del repo: i test lavorano in test-temp/
    test_temp = _repo_root() / "test-temp"
    test_temp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(test_temp.resolve()))

    # Strict disattivo: qui vogliamo verificare il CAPABILITY GATE.
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    monkeypatch.delenv("TIMMY_ALLOW_DUMMY", raising=False)

    # Richieste da ClientContext.load(require_drive_env=True) usato da tag_onboarding_context
    saf = tmp_path / "service_account.json"
    saf.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SERVICE_ACCOUNT_FILE", str(saf))
    monkeypatch.setenv("DRIVE_ID", "DUMMY_DRIVE_ID")

    # Bootstrap dummy workspace: crea output/timmy-kb-<slug> + config/book/logs dirs
    # (non è runtime: è tooling/test)
    from pipeline.workspace_bootstrap import bootstrap_dummy_workspace

    layout = bootstrap_dummy_workspace(slug)

    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(layout.repo_root_dir))

    # Il gate capability si verifica nel core: la CLI richiede strict-only e blocca prima.
    from timmy_kb.cli.tag_onboarding import tag_onboarding_main

    with pytest.raises(ConfigError) as exc_info:
        tag_onboarding_main(
            slug=slug,
            non_interactive=True,
            proceed_after_csv=False,
            dummy_mode=True,
            run_id=None,
        )
    assert "TIMMY_ALLOW_DUMMY=1" in str(exc_info.value)

    # Verifica ledger: deve contenere stop_code CAPABILITY_DUMMY_FORBIDDEN
    ledger_path = layout.config_path.parent / "ledger.db"
    assert ledger_path.exists()

    with sqlite3.connect(ledger_path) as conn:
        row = conn.execute(
            "SELECT evidence_json FROM decisions WHERE gate_name = ? ORDER BY decided_at DESC LIMIT 1",
            ("tag_onboarding",),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload.get("stop_code") == "CAPABILITY_DUMMY_FORBIDDEN"
