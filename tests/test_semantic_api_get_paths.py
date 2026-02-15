# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError, InvalidSlug
from semantic import api


def test_get_paths_rejects_blank_slug() -> None:
    with pytest.raises(ConfigError):
        api.get_paths("   ")


def test_get_paths_rejects_invalid_slug() -> None:
    with pytest.raises(InvalidSlug):
        api.get_paths("../bad")
