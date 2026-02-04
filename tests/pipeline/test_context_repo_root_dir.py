# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.env_constants import REPO_ROOT_ENV, WORKSPACE_ROOT_ENV
from pipeline.exceptions import ConfigError
from tests._helpers.workspace_paths import local_workspace_dir


def _make_repo_root(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_compute_repo_root_dir_rejects_repo_root_env_without_sentinel(tmp_path: Path) -> None:
    env_vars = {
        REPO_ROOT_ENV: str(tmp_path / "workspace"),
        WORKSPACE_ROOT_ENV: None,
    }
    logger = logging.getLogger("test.repo_root_env")
    with pytest.raises(ConfigError):
        ClientContext._compute_repo_root_dir("dummy", env_vars, logger)


def test_compute_repo_root_dir_repo_root_env_derives_output(tmp_path: Path) -> None:
    repo = _make_repo_root(tmp_path)
    env_vars = {
        REPO_ROOT_ENV: str(repo),
        WORKSPACE_ROOT_ENV: None,
    }
    logger = logging.getLogger("test.repo_root_env")
    root = ClientContext._compute_repo_root_dir("dummy", env_vars, logger)
    assert root == local_workspace_dir(repo / "output", "dummy")


def test_compute_repo_root_dir_workspace_root_env_placeholder(tmp_path: Path) -> None:
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(tmp_path / "output" / "timmy-kb-<slug>"),
    }
    logger = logging.getLogger("test.workspace_root_env")
    root = ClientContext._compute_repo_root_dir("acme", env_vars, logger)
    assert root == local_workspace_dir(tmp_path / "output", "acme")


def test_compute_repo_root_dir_rejects_workspace_with_sentinel(tmp_path: Path) -> None:
    workspace_root = tmp_path / "timmy-kb-acme"
    (workspace_root / ".git").mkdir(parents=True, exist_ok=True)
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(workspace_root),
    }
    logger = logging.getLogger("test.workspace_root_env")
    with pytest.raises(ConfigError):
        ClientContext._compute_repo_root_dir("acme", env_vars, logger)


def test_compute_repo_root_dir_strict_rejects_noncanonical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(tmp_path / "output"),
    }
    logger = logging.getLogger("test.workspace_root_env")
    with pytest.raises(ConfigError) as excinfo:
        ClientContext._compute_repo_root_dir("acme", env_vars, logger)
    assert excinfo.value.code == "workspace.root.invalid"


def test_compute_repo_root_dir_strict_accepts_canonical_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(local_workspace_dir(tmp_path / "output", "<slug>")),
    }
    logger = logging.getLogger("test.workspace_root_env")
    root = ClientContext._compute_repo_root_dir("acme", env_vars, logger)
    assert root == local_workspace_dir(tmp_path / "output", "acme")


def test_compute_workspace_root_dir_resolves_slug_macro(tmp_path: Path) -> None:
    workspace_root = tmp_path / "timmy-kb-acme"
    workspace_root.mkdir()
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(workspace_root).replace("acme", "<slug>"),
    }
    logger = logging.getLogger("test.workspace_root_env")
    root = ClientContext._compute_workspace_root_dir("acme", env_vars, logger)
    assert root == workspace_root
