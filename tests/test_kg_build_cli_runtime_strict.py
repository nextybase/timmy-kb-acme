# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from tests.conftest import DUMMY_SLUG
from timmy_kb.cli import kg_build


def test_kg_build_cli_fails_without_config_and_does_not_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / f"timmy-kb-{DUMMY_SLUG}"
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))

    args = argparse.Namespace(
        slug=DUMMY_SLUG,
        slug_pos=None,
        workspace=None,
        namespace=None,
        run_id=None,
        require_env=False,
    )

    with pytest.raises(ConfigError):
        kg_build.main(args)

    config_dir = repo_root / "config"
    config_path = config_dir / "config.yaml"
    assert not config_dir.exists()
    assert not config_path.exists()
