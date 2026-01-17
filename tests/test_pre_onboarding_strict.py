# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from timmy_kb.cli import pre_onboarding


def test_ensure_local_workspace_for_ui_merge_failure_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "workspace"
    template_root = tmp_path / "template"
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\n", encoding="utf-8")

    monkeypatch.setenv("REPO_ROOT_DIR", str(workspace_root))
    monkeypatch.setenv("TEMPLATE_CONFIG_ROOT", str(template_root))

    def _boom(*_args, **_kwargs):
        raise ConfigError("merge failed")

    monkeypatch.setattr(pre_onboarding, "merge_client_config_from_template", _boom)

    with pytest.raises(ConfigError):
        pre_onboarding.ensure_local_workspace_for_ui("dummy", client_name="Dummy")
