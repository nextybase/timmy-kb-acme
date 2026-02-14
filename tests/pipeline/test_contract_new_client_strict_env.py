# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pipeline.capabilities.new_client import (
    _scoped_workspace_env,
    _vision_pdf_path,
    create_new_client_workspace,
    run_vision_provision_for_client,
)
from pipeline.exceptions import ConfigError


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

    monkeypatch.setattr(
        "pipeline.capabilities.new_client.run_system_self_check", lambda _p: SimpleNamespace(ok=True, items=[])
    )

    def _fake_run_control_plane_tool(
        *, tool_module: str, slug: str, action: str, args: list[str] | None = None
    ) -> dict[str, Any]:
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
    assert not Path(result["semantic_mapping_path"]).exists()


def test_new_client_requires_workspace_root_env_even_non_strict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    slug = "beta"
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    monkeypatch.delenv("TIMMY_ALLOW_BOOTSTRAP", raising=False)
    monkeypatch.delenv("WORKSPACE_ROOT_DIR", raising=False)

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "pipeline.capabilities.new_client.run_system_self_check", lambda _p: SimpleNamespace(ok=True, items=[])
    )

    def _fake_run_control_plane_tool(
        *, tool_module: str, slug: str, action: str, args: list[str] | None = None
    ) -> dict[str, Any]:
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

    with pytest.raises(ConfigError, match="WORKSPACE_ROOT_DIR obbligatorio"):
        create_new_client_workspace(
            slug=slug,
            client_name="Beta",
            pdf_bytes=b"%PDF-1.4\n%fake\n",
            repo_root=repo_root,
            vision_model="dummy",
            enable_drive=False,
            ui_allow_local_only=True,
            ensure_drive_minimal=None,
            run_control_plane_tool=_fake_run_control_plane_tool,
            progress=None,
        )


def test_scoped_workspace_env_restores_bootstrap_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace_root = tmp_path / "timmy-kb-restore"
    workspace_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TIMMY_ALLOW_BOOTSTRAP", "keep")
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", "old_workspace")
    monkeypatch.setenv("REPO_ROOT_DIR", "old_repo")

    with _scoped_workspace_env(workspace_root=workspace_root):
        assert os.environ["WORKSPACE_ROOT_DIR"] == str(workspace_root)
        assert os.environ["TIMMY_ALLOW_BOOTSTRAP"] == "1"
        assert "REPO_ROOT_DIR" not in os.environ

    assert os.environ["TIMMY_ALLOW_BOOTSTRAP"] == "keep"
    assert os.environ["WORKSPACE_ROOT_DIR"] == "old_workspace"
    assert os.environ["REPO_ROOT_DIR"] == "old_repo"


def test_run_vision_provision_phase_b_requires_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    slug = "acme"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    ws_root = tmp_path / f"timmy-kb-{slug}"
    for name in ("raw", "normalized", "logs", "semantic", "book", "config"):
        (ws_root / name).mkdir(parents=True, exist_ok=True)
    (ws_root / "book" / "README.md").write_text("# README\n", encoding="utf-8")
    (ws_root / "book" / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (ws_root / "config" / "config.yaml").write_text("meta:\n  client_name: ACME\n", encoding="utf-8")

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(ws_root))

    class _FakeClientContext:
        @staticmethod
        def load(**_kwargs: Any) -> Any:
            return SimpleNamespace(slug=slug, repo_root_dir=ws_root)

    monkeypatch.setattr("pipeline.capabilities.new_client.ClientContext", _FakeClientContext)
    monkeypatch.setattr(
        "pipeline.capabilities.new_client._run_tool_with_repo_env",
        lambda **_kwargs: {"payload": {"status": "ok", "errors": []}},
    )

    with pytest.raises(ConfigError, match="semantic/semantic_mapping.yaml mancante dopo Vision"):
        run_vision_provision_for_client(
            slug=slug,
            repo_root=repo_root,
            vision_model="dummy",
            run_control_plane_tool=lambda **_kwargs: {"payload": {"status": "ok"}},
            progress=None,
        )


def test_run_vision_provision_reloads_context_after_tool_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    slug = "acme"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    ws_root = tmp_path / f"timmy-kb-{slug}"
    for name in ("raw", "normalized", "logs", "semantic", "book", "config"):
        (ws_root / name).mkdir(parents=True, exist_ok=True)
    (ws_root / "book" / "README.md").write_text("# README\n", encoding="utf-8")
    (ws_root / "book" / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (ws_root / "config" / "config.yaml").write_text("meta:\n  client_name: ACME\n", encoding="utf-8")
    (ws_root / "semantic" / "semantic_mapping.yaml").write_text("areas:\n  - key: Area One\n", encoding="utf-8")

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(ws_root))

    calls = {"count": 0}

    class _FakeClientContext:
        @staticmethod
        def load(**_kwargs: Any) -> Any:
            calls["count"] += 1
            return SimpleNamespace(slug=slug, repo_root_dir=ws_root)

    monkeypatch.setattr("pipeline.capabilities.new_client.ClientContext", _FakeClientContext)
    monkeypatch.setattr(
        "pipeline.capabilities.new_client._run_tool_with_repo_env",
        lambda **_kwargs: {"payload": {"status": "ok", "errors": []}},
    )

    result = run_vision_provision_for_client(
        slug=slug,
        repo_root=repo_root,
        vision_model="dummy",
        run_control_plane_tool=lambda **_kwargs: {"payload": {"status": "ok"}},
        progress=None,
    )

    assert calls["count"] == 2
    assert result["semantic_mapping_path"] == str(ws_root / "semantic" / "semantic_mapping.yaml")


def test_vision_pdf_path_uses_layout_canonical_path(tmp_path: Path) -> None:
    workspace = tmp_path / "timmy-kb-acme"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    layout = SimpleNamespace(
        slug="acme",
        repo_root_dir=workspace,
        config_path=config_dir / "config.yaml",
        vision_pdf=config_dir / "VisionStatement.pdf",
    )

    resolved = _vision_pdf_path(layout)
    assert resolved == config_dir / "VisionStatement.pdf"


def test_vision_pdf_path_fails_when_layout_has_no_vision_pdf(tmp_path: Path) -> None:
    workspace = tmp_path / "timmy-kb-acme"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    layout = SimpleNamespace(
        slug="acme",
        repo_root_dir=workspace,
        config_path=config_dir / "config.yaml",
        vision_pdf=None,
    )

    with pytest.raises(ConfigError, match="missing vision_pdf path"):
        _vision_pdf_path(layout)
