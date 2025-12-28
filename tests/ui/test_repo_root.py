# SPDX-License-Identifier: GPL-3.0-or-later
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
