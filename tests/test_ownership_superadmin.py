# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from pipeline.ownership import get_global_superadmins


def test_global_superadmins_empty(monkeypatch):
    monkeypatch.delenv("TIMMY_GLOBAL_SUPERADMINS", raising=False)
    assert get_global_superadmins() == []


def test_global_superadmins_parsing(monkeypatch):
    monkeypatch.setenv("TIMMY_GLOBAL_SUPERADMINS", "a@example.com, b@example.com ")
    assert get_global_superadmins() == ["a@example.com", "b@example.com"]


def test_global_superadmins_invalid(monkeypatch):
    monkeypatch.setenv("TIMMY_GLOBAL_SUPERADMINS", "bad email")
    with pytest.raises(ConfigError) as exc:
        get_global_superadmins()
    assert exc.value.code == "ownership.superadmin.invalid"
