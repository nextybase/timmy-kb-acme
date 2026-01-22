# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


def _write_minimal_workspace(root: Path) -> None:
    (root / "raw").mkdir(parents=True)
    (root / "semantic").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "config" / "config.yaml").write_text("meta:\n  client_name: dummy\n", encoding="utf-8")
    (root / "book").mkdir(parents=True)
    (root / "book" / "README.md").write_text("# README\n", encoding="utf-8")
    (root / "book" / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (root / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")


def test_from_context_ignores_context_dir_overrides(tmp_path: Path) -> None:
    workspace_root = tmp_path / "timmy-kb-dummy"
    _write_minimal_workspace(workspace_root)
    outside = tmp_path / "outside"
    outside.mkdir()

    ctx = SimpleNamespace(
        slug="dummy",
        repo_root_dir=workspace_root,
        base_dir=workspace_root,
        raw_dir=outside / "raw",
        book_dir=outside / "book",
        semantic_dir=outside / "semantic",
        logs_dir=outside / "logs",
        config_path=outside / "config" / "config.yaml",
        mapping_path=outside / "semantic" / "semantic_mapping.yaml",
        client_name="Dummy",
        env=None,
    )

    layout = WorkspaceLayout.from_context(ctx)  # type: ignore[arg-type]
    assert layout.base_dir == workspace_root
    assert layout.raw_dir == workspace_root / "raw"
    assert layout.book_dir == workspace_root / "book"
    assert layout.semantic_dir == workspace_root / "semantic"
    assert layout.logs_dir == workspace_root / "logs"


def test_from_context_requires_repo_root_dir_even_if_base_dir_present(tmp_path: Path) -> None:
    workspace_root = tmp_path / "timmy-kb-dummy"
    _write_minimal_workspace(workspace_root)
    ctx = SimpleNamespace(slug="dummy", repo_root_dir=None, base_dir=workspace_root)
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_context(ctx)  # type: ignore[arg-type]
