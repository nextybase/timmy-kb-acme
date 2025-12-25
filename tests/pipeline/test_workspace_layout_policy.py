# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline.exceptions import WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


def test_from_workspace_missing_directory_raises_workspace_not_found(tmp_path: Path) -> None:
    missing_root = tmp_path / "timmy-kb-missing"
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_workspace(missing_root)


def test_from_workspace_missing_config_file_triggers_workspace_layout_invalid(tmp_path: Path) -> None:
    workspace = tmp_path / "timmy-kb-invalid-config"
    raw_dir = workspace / "raw"
    book_dir = workspace / "book"
    semantic_dir = workspace / "semantic"
    logs_dir = workspace / "logs"
    config_dir = workspace / "config"
    raw_dir.mkdir(parents=True)
    book_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (book_dir / "README.md").write_text("dummy")
    (book_dir / "SUMMARY.md").write_text("dummy")
    # intentionally omit config/config.yaml

    with pytest.raises(WorkspaceLayoutInvalid):
        WorkspaceLayout.from_workspace(workspace)

    assert not (config_dir / "config.yaml").exists()


def test_from_workspace_missing_book_readme_triggers_workspace_layout_invalid(tmp_path: Path) -> None:
    workspace = tmp_path / "timmy-kb-missing-readme"
    raw_dir = workspace / "raw"
    book_dir = workspace / "book"
    semantic_dir = workspace / "semantic"
    logs_dir = workspace / "logs"
    config_dir = workspace / "config"
    raw_dir.mkdir(parents=True)
    book_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (config_dir / "config.yaml").write_text("config")
    (book_dir / "SUMMARY.md").write_text("summary")
    # README intentionally missing

    with pytest.raises(WorkspaceLayoutInvalid):
        WorkspaceLayout.from_workspace(workspace)

    assert not (book_dir / "README.md").exists()
