# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import ConfigError
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger
from tests._helpers.workspace_paths import local_workspace_dir
from timmy_kb.cli import pre_onboarding


def test_ensure_local_workspace_for_ui_merge_failure_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "dummy"
    workspace_root = local_workspace_dir(tmp_path, slug)
    template_root = tmp_path / "template"
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\n", encoding="utf-8")

    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(workspace_root))
    monkeypatch.setenv("TEMPLATE_CONFIG_ROOT", str(template_root))

    def _boom(*_args, **_kwargs):
        raise ConfigError("merge failed")

    monkeypatch.setattr(pre_onboarding, "merge_client_config_from_template", _boom)

    with pytest.raises(ConfigError):
        pre_onboarding.ensure_local_workspace_for_ui(slug, client_name="Dummy")


def test_blank_slug_blocks_pre_onboarding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica che uno slug vuoto blocchi il pre-onboarding senza effetti collaterali."""
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(tmp_path / "timmy-kb-"))

    with pytest.raises(ConfigError):
        pre_onboarding.ensure_local_workspace_for_ui("", client_name="NoSlug")

    assert not any(tmp_path.iterdir())


def test_pre_onboarding_blocks_when_vision_pdf_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se VisionStatement.pdf è dichiarato nel template ma non presente, la run blocca."""
    slug = "vision"
    workspace_template = tmp_path / "timmy-kb-<slug>"
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(workspace_template))

    original_get_client_config = pre_onboarding.get_client_config

    def _force_vision_conf(ctx: Any) -> dict[str, Any] | None:
        cfg = original_get_client_config(ctx) or {}
        ai_section = cfg.setdefault("ai", {})
        vision_section = ai_section.setdefault("vision", {})
        vision_section["vision_statement_pdf"] = "config/VisionStatement.pdf"
        return cfg

    monkeypatch.setattr(pre_onboarding, "get_client_config", _force_vision_conf)

    with pytest.raises(ConfigError):
        pre_onboarding.pre_onboarding_main(
            slug=slug,
            client_name="Vision Client",
            interactive=False,
            dry_run=True,
            run_id="vision-test",
        )

    layout = WorkspaceLayout.from_slug(slug=slug, require_drive_env=False)
    conn = decision_ledger.open_ledger(layout)
    try:
        row = conn.execute(
            "SELECT verdict, stop_code, evidence_json FROM decisions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == decision_ledger.DECISION_DENY
        assert row[1] == decision_ledger.STOP_CODE_VISION_ARTIFACT_MISSING
        assert row[2] is not None
        evidence = json.loads(row[2])
        assert evidence.get("normative_verdict") == decision_ledger.NORMATIVE_BLOCK
    finally:
        conn.close()
