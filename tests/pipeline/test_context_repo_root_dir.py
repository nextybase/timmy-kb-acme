# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.env_constants import REPO_ROOT_ENV, WORKSPACE_ROOT_ENV
from pipeline.exceptions import ConfigError


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
    assert root == repo / "output" / "timmy-kb-dummy"


def test_compute_repo_root_dir_workspace_root_env_placeholder(tmp_path: Path) -> None:
    env_vars = {
        REPO_ROOT_ENV: None,
        WORKSPACE_ROOT_ENV: str(tmp_path / "output"),
    }
    logger = logging.getLogger("test.workspace_root_env")
    root = ClientContext._compute_repo_root_dir("acme", env_vars, logger)
    assert root == tmp_path / "output" / "timmy-kb-acme"


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
