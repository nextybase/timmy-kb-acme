# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError


def test_repo_root_dir_required_raises_when_missing() -> None:
    ctx = ClientContext(slug="acme", repo_root_dir=None)
    with pytest.raises(ConfigError) as excinfo:
        ctx.repo_root_dir_required()
    assert "repo_root_dir missing" in str(excinfo.value)


def test_config_path_required_raises_when_missing(tmp_path: Path) -> None:
    ctx = ClientContext(slug="acme", repo_root_dir=tmp_path, config_path=None)
    with pytest.raises(ConfigError) as excinfo:
        ctx.config_path_required()
    assert "config_path missing" in str(excinfo.value)


def test_mapping_path_required_raises_when_missing(tmp_path: Path) -> None:
    ctx = ClientContext(slug="acme", repo_root_dir=tmp_path, mapping_path=None)
    with pytest.raises(ConfigError) as excinfo:
        ctx.mapping_path_required()
    assert "mapping_path missing" in str(excinfo.value)
