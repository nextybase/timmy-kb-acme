# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from tests.conftest import DUMMY_SLUG


def test_load_without_bootstrap_requires_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))

    workspace_root = repo_root / "output" / f"timmy-kb-{DUMMY_SLUG}"
    expected_path = workspace_root / "config" / "config.yaml"
    with pytest.raises(ConfigError) as exc_info:
        ClientContext.load(
            DUMMY_SLUG,
            require_env=False,
            bootstrap_config=False,
        )
    err = exc_info.value
    assert "config/config.yaml" in str(err)
    assert str(expected_path) in str(err)
    assert getattr(err, "file_path", None) == expected_path
