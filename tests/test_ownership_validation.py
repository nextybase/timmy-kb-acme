# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.ownership import load_ownership, validate_ownership


def _write_yaml(path: Path, text: str) -> None:
    safe_write_text(path, text, encoding="utf-8")


def test_load_ownership_normalizes_roles(tmp_path):
    slug = "demo"
    ownership_path = tmp_path / "clients" / slug / "ownership.yaml"
    _write_yaml(
        ownership_path,
        """schema_version: "1"
owners:
  user:
    - "@nextybase/user-channel"
""",
    )

    cfg = load_ownership(slug, tmp_path)

    assert cfg["schema_version"] == "1"
    assert cfg["slug"] == slug
    assert cfg["owners"]["user"] == ["@nextybase/user-channel"]
    assert cfg["owners"]["dev"] == []
    assert cfg["owners"]["architecture"] == []


def test_validate_ownership_unknown_role():
    with pytest.raises(ConfigError) as exc:
        validate_ownership({"owners": {"ops": ["@x"]}}, slug="demo")
    assert exc.value.code == "ownership.invalid"


def test_validate_ownership_slug_mismatch():
    with pytest.raises(ConfigError) as exc:
        validate_ownership({"slug": "other", "owners": {}}, slug="demo")
    assert exc.value.code == "ownership.invalid"
