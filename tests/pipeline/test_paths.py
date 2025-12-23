# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.paths import (
    clients_db_paths,
    ensure_src_on_sys_path,
    get_repo_root,
    global_logs_dir,
    preview_logs_dir,
    workspace_paths,
)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_get_repo_root_env_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo))
    found = get_repo_root()
    assert found == repo


def test_get_repo_root_env_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path / "missing"))
    with pytest.raises(ConfigError):
        get_repo_root()


def test_get_repo_root_detects_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.chdir(repo)
    found = get_repo_root()
    assert found == repo


def test_workspace_paths_create(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    paths = workspace_paths("acme", repo_root=repo, create=True)
    assert paths.workspace_root == repo / "output" / "timmy-kb-acme"
    assert paths.raw_dir.exists()
    assert paths.book_dir.exists()
    assert paths.semantic_dir.exists()
    assert paths.config_dir.exists()
    assert paths.logs_dir.exists()
    assert paths.preview_logs_dir.exists()


def test_workspace_paths_invalid_slug(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with pytest.raises((ConfigError, InvalidSlug)):
        workspace_paths("INVALID SLUG", repo_root=repo)


def test_global_logs_dir(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    path = global_logs_dir(repo)
    assert path == repo / ".timmy_kb" / "logs"
    assert path.exists() and path.is_dir()


def test_clients_db_paths(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    dir_path, file_path = clients_db_paths(repo)
    assert dir_path == repo / "clients_db"
    assert file_path == dir_path / "clients.yaml"
    assert dir_path.exists()


def test_preview_logs_dir_override_absolute(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    override = tmp_path / "custom" / "preview_logs"
    path = preview_logs_dir(repo, override=override)
    assert path.resolve() == override.resolve()
    assert path.exists()


def test_preview_logs_dir_invalid_relative(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with pytest.raises(ConfigError):
        preview_logs_dir(repo, override=Path("..") / "outside")


def test_ensure_src_on_sys_path_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    src_dir = repo / "src"
    src_dir.mkdir()
    original = list(sys.path)
    monkeypatch.setattr(sys, "path", [])
    ensure_src_on_sys_path(repo)
    assert str(src_dir) in sys.path
    ensure_src_on_sys_path(repo)
    assert sys.path.count(str(src_dir)) == 1
    monkeypatch.setattr(sys, "path", original)
