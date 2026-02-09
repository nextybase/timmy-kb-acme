# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from tests._helpers.workspace_paths import local_workspace_dir
from tests.conftest import DUMMY_SLUG
from timmy_kb.cli import kg_build


def test_kg_build_cli_fails_without_config_and_does_not_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    # Strict runtime: serve un workspace root esplicito (no bootstrap/override impliciti).
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(repo_root))

    # Il CLI usa una REPO_ROOT calcolata dal file; in test la rendiamo deterministica.
    monkeypatch.setattr(kg_build, "REPO_ROOT", repo_root, raising=False)

    args = argparse.Namespace(
        slug=DUMMY_SLUG,
        slug_pos=None,
        workspace=None,
        namespace=None,
        run_id=None,
        # Nuovo contract: è require_env (non require_drive_env).
        require_env=False,
    )

    with pytest.raises(ConfigError):
        kg_build.main(args)

    workspace_root = local_workspace_dir(repo_root / "output", DUMMY_SLUG)
    config_dir = workspace_root / "config"
    config_path = config_dir / "config.yaml"
    assert not config_dir.exists()
    assert not config_path.exists()
