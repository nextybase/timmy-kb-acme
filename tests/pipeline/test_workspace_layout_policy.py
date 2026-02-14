# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest

from pipeline import workspace_layout as workspace_layout_mod
from pipeline.exceptions import WorkspaceLayoutInconsistent, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout
from tests._helpers.workspace_paths import local_workspace_dir


def test_from_workspace_missing_directory_raises_workspace_not_found(tmp_path: Path) -> None:
    missing_root = local_workspace_dir(tmp_path, "missing")
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_workspace(missing_root, slug="missing")


def test_from_workspace_missing_config_file_triggers_workspace_layout_invalid(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path, "invalid-config")
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
    (semantic_dir / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    # intentionally omit config/config.yaml

    with pytest.raises(WorkspaceLayoutInvalid):
        WorkspaceLayout.from_workspace(workspace, slug="invalid-config")

    assert not (config_dir / "config.yaml").exists()


def test_from_workspace_missing_book_readme_triggers_workspace_layout_invalid(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path, "missing-readme")
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
    (semantic_dir / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    # README intentionally missing

    with pytest.raises(WorkspaceLayoutInvalid):
        WorkspaceLayout.from_workspace(workspace, slug="missing-readme")

    assert not (book_dir / "README.md").exists()


def test_from_workspace_missing_semantic_mapping_triggers_workspace_layout_invalid(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path, "missing-mapping")
    raw_dir = workspace / "raw"
    normalized_dir = workspace / "normalized"
    book_dir = workspace / "book"
    semantic_dir = workspace / "semantic"
    logs_dir = workspace / "logs"
    config_dir = workspace / "config"
    raw_dir.mkdir(parents=True)
    normalized_dir.mkdir(parents=True)
    book_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (config_dir / "config.yaml").write_text("config")
    (book_dir / "README.md").write_text("readme")
    (book_dir / "SUMMARY.md").write_text("summary")
    # semantic_mapping.yaml intentionally missing

    with pytest.raises(WorkspaceLayoutInvalid) as excinfo:
        WorkspaceLayout.from_workspace(workspace, slug="missing-mapping")

    assert "semantic/semantic_mapping.yaml" in str(excinfo.value)


def test_layout_consistency_validator_rejects_none_mapping_path(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path, "none-mapping")
    raw_dir = workspace / "raw"
    normalized_dir = workspace / "normalized"
    book_dir = workspace / "book"
    semantic_dir = workspace / "semantic"
    logs_dir = workspace / "logs"
    config_dir = workspace / "config"
    raw_dir.mkdir(parents=True)
    normalized_dir.mkdir(parents=True)
    book_dir.mkdir(parents=True)
    semantic_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text("config")
    (book_dir / "README.md").write_text("readme")
    (book_dir / "SUMMARY.md").write_text("summary")

    with pytest.raises(WorkspaceLayoutInconsistent):
        workspace_layout_mod._ensure_layout_consistency(  # type: ignore[arg-type]
            slug="none-mapping",
            workspace_root=workspace,
            raw_dir=raw_dir,
            normalized_dir=normalized_dir,
            config_path=config_path,
            book_dir=book_dir,
            logs_dir=logs_dir,
            semantic_dir=semantic_dir,
            mapping_path=None,
        )
