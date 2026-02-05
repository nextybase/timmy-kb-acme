# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.paths import clients_db_paths, get_repo_root, global_logs_dir, preview_logs_dir
from tests._helpers.workspace_paths import local_workspace_dir


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_get_repo_root_env_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo))
    monkeypatch.chdir(repo)
    found = get_repo_root()
    assert found == repo


def test_get_repo_root_env_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path / "missing"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        get_repo_root()


def test_get_repo_root_env_missing_sentinel_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    workspace_like = local_workspace_dir(repo / "output", "dummy")
    workspace_like.mkdir(parents=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(workspace_like))
    monkeypatch.chdir(repo)
    with pytest.raises(ConfigError):
        get_repo_root()


def test_get_repo_root_ignores_env_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    monkeypatch.setenv("REPO_ROOT_DIR", str(other))
    monkeypatch.chdir(repo)
    found = get_repo_root(allow_env=False)
    assert found == repo


def test_get_repo_root_detects_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)
    monkeypatch.chdir(repo)
    found = get_repo_root()
    assert found == repo


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
