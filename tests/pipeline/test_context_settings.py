# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.context import _safe_settings_get
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings


def _strict_settings() -> Settings:
    return Settings(config_path=Path("config/config.yaml"), data={"meta": {"client_name": "strict-client"}})


def test_safe_settings_get_strict_requires_settings(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    with pytest.raises(ConfigError) as excinfo:
        _safe_settings_get({"client_name": "beta"}, "client_name")
    assert excinfo.value.code == "config.shape.invalid"


def test_safe_settings_get_strict_reads_typed_property(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    settings = _strict_settings()
    assert _safe_settings_get(settings, "client_name") == "strict-client"


def test_safe_settings_get_non_strict_allows_mapping(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    assert _safe_settings_get({"client_name": "beta"}, "client_name") == "beta"
