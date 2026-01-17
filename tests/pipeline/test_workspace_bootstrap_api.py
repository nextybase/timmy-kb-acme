# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline import workspace_bootstrap
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


@pytest.fixture
def dummy_context(tmp_path: Path) -> ClientContext:
    root = tmp_path / "timmy-kb-dummy"
    return ClientContext(
        slug="dummy",
        repo_root_dir=root,
        base_dir=root,
        raw_dir=root / "raw",
        md_dir=root / "book",
    )


def test_workspace_bootstrap_module_importable() -> None:
    assert workspace_bootstrap.bootstrap_client_workspace
    assert workspace_bootstrap.bootstrap_dummy_workspace
    assert workspace_bootstrap.migrate_or_repair_workspace


def test_migrate_or_repair_workspace_raises(dummy_context: ClientContext) -> None:
    with pytest.raises(WorkspaceNotFound):
        workspace_bootstrap.migrate_or_repair_workspace(dummy_context)


def test_bootstrap_client_workspace_requires_repo_root_dir() -> None:
    context = ClientContext(slug="dummy")
    context.repo_root_dir = None
    with pytest.raises(WorkspaceNotFound):
        workspace_bootstrap.bootstrap_client_workspace(context)


def test_bootstrap_dummy_workspace_creates_minimal_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(tmp_path))
    layout = workspace_bootstrap.bootstrap_dummy_workspace("dummy")
    workspace = tmp_path / "output" / "timmy-kb-dummy"
    assert workspace.exists()
    assert (workspace / "config" / "config.yaml").is_file()
    assert (workspace / "book" / "README.md").is_file()
    assert (workspace / "book" / "SUMMARY.md").is_file()
    assert (workspace / "semantic").is_dir()
    assert (workspace / "raw").is_dir()
    assert isinstance(layout, WorkspaceLayout)


def test_bootstrap_dummy_workspace_invalid_after_corruption(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TIMMY_KB_DUMMY_OUTPUT_ROOT", str(tmp_path))
    layout = workspace_bootstrap.bootstrap_dummy_workspace("dummy")
    workspace = layout.repo_root_dir
    readme = workspace / "book" / "README.md"
    readme.unlink()
    with pytest.raises(WorkspaceLayoutInvalid):
        WorkspaceLayout.from_workspace(workspace, slug="dummy")


def _make_client_context(tmp_path: Path, slug: str) -> ClientContext:
    base = tmp_path / "output" / f"timmy-kb-{slug}"
    return ClientContext(slug=slug, repo_root_dir=base, base_dir=base)


def test_bootstrap_client_workspace_creates_valid_layout(tmp_path: Path) -> None:
    slug = "test-client"
    context = _make_client_context(tmp_path, slug)
    layout = workspace_bootstrap.bootstrap_client_workspace(context)
    workspace = tmp_path / "output" / f"timmy-kb-{slug}"
    assert workspace.exists()
    assert (workspace / "config" / "config.yaml").is_file()
    assert (workspace / "book" / "README.md").is_file()
    assert (workspace / "book" / "SUMMARY.md").is_file()
    assert (workspace / "semantic").is_dir()
    assert (workspace / "raw").is_dir()
    assert (workspace / "logs").is_dir()
    assert isinstance(layout, WorkspaceLayout)
    WorkspaceLayout.from_context(context)


def test_bootstrap_client_workspace_is_idempotent(tmp_path: Path) -> None:
    slug = "test-client"
    context = _make_client_context(tmp_path, slug)
    workspace_bootstrap.bootstrap_client_workspace(context)
    second_layout = workspace_bootstrap.bootstrap_client_workspace(context)
    workspace = tmp_path / "output" / f"timmy-kb-{slug}"
    for text_file in (
        workspace / "config" / "config.yaml",
        workspace / "book" / "README.md",
        workspace / "book" / "SUMMARY.md",
    ):
        assert text_file.read_text(encoding="utf-8")
    assert second_layout.repo_root_dir == workspace


def test_bootstrap_client_workspace_missing_repo_template_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_repo_root = tmp_path / "repo-missing-template"
    monkeypatch.setattr(workspace_bootstrap, "_project_root", lambda: missing_repo_root)
    context = _make_client_context(tmp_path, "no-template")
    with pytest.raises(ConfigError):
        workspace_bootstrap.bootstrap_client_workspace(context)
    assert not (context.repo_root_dir / "config" / "config.yaml").exists()


def test_migrate_or_repair_workspace_missing_repo_template_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_repo_root = tmp_path / "repo-missing-template"
    monkeypatch.setattr(workspace_bootstrap, "_project_root", lambda: missing_repo_root)
    context = _make_client_context(tmp_path, "no-template")
    context.repo_root_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ConfigError):
        workspace_bootstrap.migrate_or_repair_workspace(context)
    assert not (context.repo_root_dir / "config" / "config.yaml").exists()
