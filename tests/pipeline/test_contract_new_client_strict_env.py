# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.capabilities.new_client import create_new_client_workspace


def test_new_client_strict_does_not_require_workspace_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    In strict runtime non dobbiamo dipendere da TIMMY_ALLOW_WORKSPACE_OVERRIDE
    (che nei test harness oggi è spesso forzato globalmente).
    """
    slug = "acme"

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.delenv("TIMMY_ALLOW_WORKSPACE_OVERRIDE", raising=False)

    monkeypatch.setenv("TIMMY_ALLOW_BOOTSTRAP", "1")

    ws_root = tmp_path / f"timmy-kb-{slug}"
    ws_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(ws_root))

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("pipeline.capabilities.new_client.run_system_self_check", lambda _p: SimpleNamespace(ok=True, items=[]))

    def _fake_run_control_plane_tool(*, tool_module: str, slug: str, action: str, args: list[str] | None = None) -> dict[str, Any]:
        return {
            "payload": {
                "action": action,
                "status": "ok",
                "returncode": 0,
                "errors": [],
                "warnings": [],
                "artifacts": [],
            }
        }

    result = create_new_client_workspace(
        slug=slug,
        client_name="ACME",
        pdf_bytes=b"%PDF-1.4\n%fake\n",
        repo_root=repo_root,
        vision_model="dummy",
        enable_drive=False,
        ui_allow_local_only=True,
        ensure_drive_minimal=None,
        run_control_plane_tool=_fake_run_control_plane_tool,
        progress=None,
    )

    assert Path(result["workspace_root_dir"]).name == f"timmy-kb-{slug}"
