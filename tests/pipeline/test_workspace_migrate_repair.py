# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline import workspace_bootstrap
from pipeline.context import ClientContext
from pipeline.exceptions import WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


def _make_context(base: Path, slug: str) -> ClientContext:
    return ClientContext(
        slug=slug,
        repo_root_dir=base,
        config_path=base / "config" / "config.yaml",
    )


def test_migrate_or_repair_workspace_raises_not_found(tmp_path: Path) -> None:
    slug = "missing-client"
    context = _make_context(tmp_path / f"timmy-kb-{slug}", slug)
    with pytest.raises(WorkspaceNotFound):
        workspace_bootstrap.migrate_or_repair_workspace(context)


def test_migrate_or_repair_workspace_repairs_missing_assets(tmp_path: Path) -> None:
    slug = "repairable"
    context = _make_context(tmp_path / f"timmy-kb-{slug}", slug)
    workspace_bootstrap.bootstrap_client_workspace(context)
    workspace = context.repo_root_dir
    assert workspace is not None
    # remove README and config to simulate corruption
    (workspace / "book" / "README.md").unlink()
    (workspace / "config" / "config.yaml").unlink()

    repaired = workspace_bootstrap.migrate_or_repair_workspace(context)

    assert (workspace / "book" / "README.md").is_file()
    assert (workspace / "config" / "config.yaml").is_file()
    assert isinstance(repaired, WorkspaceLayout)
    WorkspaceLayout.from_context(context)


def test_migrate_or_repair_workspace_is_idempotent(tmp_path: Path) -> None:
    slug = "repairable-idempotent"
    context = _make_context(tmp_path / f"timmy-kb-{slug}", slug)
    workspace_bootstrap.bootstrap_client_workspace(context)
    workspace_bootstrap.migrate_or_repair_workspace(context)
    layout = workspace_bootstrap.migrate_or_repair_workspace(context)
    assert isinstance(layout, WorkspaceLayout)
