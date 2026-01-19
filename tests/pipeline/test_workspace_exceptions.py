# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, WorkspaceLayoutInconsistent, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


def test_workspace_exceptions_are_config_errors() -> None:
    assert issubclass(WorkspaceNotFound, ConfigError)
    assert issubclass(WorkspaceLayoutInvalid, ConfigError)
    assert issubclass(WorkspaceLayoutInconsistent, ConfigError)


def test_workspace_exception_str_contains_context() -> None:
    exc = WorkspaceNotFound(
        "workspace root mancante",
        slug="timmy-kb-acme",
        file_path=Path("config/config.yaml"),
    )
    text = str(exc)
    assert "slug=timmy-kb-acme" in text
    assert "file=config.yaml" in text


def test_workspace_layout_missing_root_raises_workspace_not_found() -> None:
    ctx = ClientContext(slug="dummy")
    ctx.repo_root_dir = None
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_context(ctx)


def test_workspace_layout_missing_repo_root_dir_raises(tmp_path: Path) -> None:
    ctx = ClientContext(slug="dummy")
    ctx.repo_root_dir = None
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_context(ctx)
