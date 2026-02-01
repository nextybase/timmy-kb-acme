# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.workspace_layout import WorkspaceLayout
from tests.ui.stub_helpers import install_streamlit_stub


def _load_new_client(monkeypatch: pytest.MonkeyPatch):
    install_streamlit_stub(monkeypatch)
    sys.modules.pop("ui.pages.new_client", None)
    return importlib.import_module("ui.pages.new_client")


def _make_workspace(tmp_path: Path, slug: str) -> Path:
    workspace_root = tmp_path / "output" / f"timmy-kb-{slug}"
    (workspace_root / "config").mkdir(parents=True, exist_ok=True)
    (workspace_root / "book").mkdir(parents=True, exist_ok=True)
    (workspace_root / "book" / "README.md").write_text("# Book\n", encoding="utf-8")
    (workspace_root / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (workspace_root / "logs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "raw").mkdir(parents=True, exist_ok=True)
    (workspace_root / "normalized").mkdir(parents=True, exist_ok=True)
    (workspace_root / "semantic").mkdir(parents=True, exist_ok=True)
    return workspace_root


def test_mirror_repo_config_missing_template_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new_client = _load_new_client(monkeypatch)

    slug = "dummy"
    template_root = tmp_path
    workspace_root = _make_workspace(tmp_path, slug)
    client_cfg_dir = workspace_root / "config"
    (client_cfg_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")
    layout = WorkspaceLayout.from_workspace(workspace=workspace_root, slug=slug)

    monkeypatch.setattr(new_client, "get_repo_root", lambda: template_root)

    with pytest.raises(ConfigError):
        new_client._mirror_repo_config_into_client(slug, layout)
    assert (client_cfg_dir / "config.yaml").is_file()


def test_mirror_repo_config_merge_failure_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    new_client = _load_new_client(monkeypatch)

    slug = "dummy"
    template_root = tmp_path
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\n", encoding="utf-8")
    workspace_root = _make_workspace(tmp_path, slug)
    client_cfg_dir = workspace_root / "config"
    (client_cfg_dir / "config.yaml").write_text("client_name: dummy\n", encoding="utf-8")
    layout = WorkspaceLayout.from_workspace(workspace=workspace_root, slug=slug)

    monkeypatch.setattr(new_client, "get_repo_root", lambda: template_root)

    def _boom(*_args, **_kwargs):
        raise ValueError("merge failed")

    monkeypatch.setattr(new_client, "deep_merge_dict", _boom)

    with pytest.raises(ConfigError):
        new_client._mirror_repo_config_into_client(slug, layout)
