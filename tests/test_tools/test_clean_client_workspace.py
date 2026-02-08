# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.exceptions import ConfigError
from src.tools.clean_client_workspace import _resolve_workspace_root


def test_resolve_workspace_root_expands_placeholder(tmp_path, monkeypatch):
    slug = "dummy"
    workspace_dir = tmp_path / "output" / f"timmy-kb-{slug}"
    workspace_dir.mkdir(parents=True)
    placeholder = str(workspace_dir).replace(slug, "<slug>")
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, placeholder)

    resolved = _resolve_workspace_root(slug)
    assert resolved.name == f"timmy-kb-{slug}"
    assert resolved == workspace_dir


def test_resolve_workspace_root_rejects_querystring(tmp_path, monkeypatch):
    slug = "dummy"
    bad_path = tmp_path / "output" / f"timmy-kb-{slug}?q=1"
    monkeypatch.setenv(WORKSPACE_ROOT_ENV, str(bad_path))

    with pytest.raises(ConfigError) as excinfo:
        _resolve_workspace_root(slug)

    assert excinfo.value.code == "workspace.root.invalid"
