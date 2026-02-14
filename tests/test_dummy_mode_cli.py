# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

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

    # Bootstrap dummy workspace: crea output/<workspace-name> + config/book/logs dirs
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


def test_strict_by_default_does_not_enable_dummy_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from timmy_kb.cli import tag_onboarding as mod

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("TIMMY_ALLOW_DUMMY", "1")

    requested_mode, effective_mode, rationale = mod._resolve_modes(dummy_mode=False, strict_mode=True)

    assert requested_mode == "standard"
    assert effective_mode == "standard"
    assert rationale == "checkpoint_proceeded_no_stub"


def test_build_gate_decision_record_populates_optional_stop_code() -> None:
    from timmy_kb.cli import tag_onboarding as mod

    base = dict(
        run_id="rid",
        slug="acme",
        evidence_refs=["slug:acme"],
        verdict="PASS",
        reason_code="ok",
        decided_at="2026-01-01T00:00:00Z",
    )
    rec_without = mod._build_gate_decision_record(**base)
    rec_with = mod._build_gate_decision_record(**base, stop_code="SAMPLE_STOP")

    assert rec_without.stop_code is None
    assert rec_with.stop_code == "SAMPLE_STOP"
    assert rec_with.gate_name == "tag_onboarding"
    assert rec_with.actor == "cli.tag_onboarding"
    assert rec_with.subject == "tag_onboarding"
    assert rec_with.from_state == mod.decision_ledger.STATE_SEMANTIC_INGEST
    assert rec_with.to_state == mod.decision_ledger.STATE_SEMANTIC_INGEST
    assert rec_with.decision_id


def test_strict_mode_blocks_dummy_path_even_when_capability_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from timmy_kb.cli import tag_onboarding as mod

    slug = "dummy-strict"
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("TIMMY_ALLOW_DUMMY", "1")
    monkeypatch.delenv("TIMMY_ALLOW_BOOTSTRAP", raising=False)

    workspace = tmp_path / "ws"
    normalized = workspace / "normalized"
    semantic = workspace / "semantic"
    config = workspace / "config"
    logs = workspace / "logs"
    for p in (normalized, semantic, config, logs):
        p.mkdir(parents=True, exist_ok=True)
    (config / "config.yaml").write_text("client_name: Dummy\n", encoding="utf-8")

    called = {"stub": 0}
    recorded: list[object] = []

    def _stub_phase(*_args, **_kwargs):
        called["stub"] += 1
        raise AssertionError("stub phase non deve essere eseguita in strict mode")

    fake_layout = SimpleNamespace(
        slug=slug,
        repo_root_dir=workspace,
        normalized_dir=normalized,
        semantic_dir=semantic,
        config_path=config / "config.yaml",
    )
    fake_ctx = SimpleNamespace(slug=slug, repo_root_dir=workspace, semantic_dir=semantic)
    fake_logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    fake_resources = SimpleNamespace(
        context=fake_ctx,
        repo_root_dir=workspace,
        normalized_dir=normalized,
        semantic_dir=semantic,
        logger=fake_logger,
        log_file=logs / "tag_onboarding.log",
    )

    monkeypatch.setattr(mod, "prepare_context", lambda **_kwargs: fake_resources, raising=True)
    monkeypatch.setattr(mod, "_require_layout", lambda _ctx: fake_layout, raising=True)
    monkeypatch.setattr(mod, "_require_normalized_index", lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr(mod, "emit_csv_phase", lambda *_a, **_k: semantic / "tags_reviewed.csv", raising=True)
    monkeypatch.setattr(mod, "enforce_core_artifacts", lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr(mod, "_should_proceed", lambda **_kwargs: True, raising=True)
    monkeypatch.setattr(mod, "emit_stub_phase", _stub_phase, raising=True)
    monkeypatch.setattr(
        mod.decision_ledger,
        "open_ledger",
        lambda _layout: SimpleNamespace(close=lambda: None),
        raising=True,
    )
    monkeypatch.setattr(mod.decision_ledger, "start_run", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(mod.decision_ledger, "record_normative_decision", lambda _conn, rec: recorded.append(rec))

    mod.tag_onboarding_main(
        slug=slug,
        non_interactive=True,
        proceed_after_csv=True,
        dummy_mode=True,
        run_id=None,
    )

    assert called["stub"] == 0
    assert recorded
    assert getattr(recorded[-1], "reason_code", None) == mod.REASON_DUMMY_BLOCKED_BY_STRICT
