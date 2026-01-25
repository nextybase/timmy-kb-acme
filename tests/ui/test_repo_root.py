# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import sys

from ui.utils.repo_root import get_repo_root


def test_get_repo_root_detects_marker_from_cwd(monkeypatch, tmp_path) -> None:
    project_root = tmp_path / "project"
    nested_dir = project_root / "src" / "ui"
    nested_dir.mkdir(parents=True)
    (project_root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)
    monkeypatch.delenv("REPO_ROOT_DIR", raising=False)

    assert get_repo_root(allow_env=False) == project_root


def test_get_repo_root_env_valid(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "project-env"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo))
    assert get_repo_root() == repo
    assert get_repo_root(allow_env=True) == repo


def test_get_repo_root_env_disabled(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "project-disabled"
    repo.mkdir()
    (repo / ".git").mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    monkeypatch.setenv("REPO_ROOT_DIR", str(other))
    monkeypatch.chdir(repo)
    assert get_repo_root(allow_env=False) == repo


def test_ui_modules_use_env_repo_root(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "ui-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo))

    for name in ("ui.config_store", "ui.landing_slug"):
        sys.modules.pop(name, None)

    config_store = importlib.import_module("ui.config_store")
    landing = importlib.import_module("ui.landing_slug")

    assert config_store.REPO_ROOT == repo
    assert landing.REPO_ROOT == repo
