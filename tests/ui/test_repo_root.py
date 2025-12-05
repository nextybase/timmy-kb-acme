# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from ui.utils.repo_root import _find_repo_root


def test_find_repo_root_prefers_git_marker(tmp_path) -> None:
    project_root = tmp_path / "project"
    nested_dir = project_root / "src" / "ui"
    nested_dir.mkdir(parents=True)
    (project_root / ".git").mkdir()

    assert _find_repo_root(nested_dir) == project_root


def test_find_repo_root_uses_pyproject_marker(tmp_path) -> None:
    project_root = tmp_path / "project"
    nested_dir = project_root / "app"
    nested_dir.mkdir(parents=True)
    (project_root / "pyproject.toml").touch()

    assert _find_repo_root(nested_dir) == project_root


def test_find_repo_root_fallbacks_to_cwd(tmp_path, monkeypatch) -> None:
    nested_dir = tmp_path / "orphan" / "deep"
    nested_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert _find_repo_root(nested_dir) == Path.cwd().resolve()
