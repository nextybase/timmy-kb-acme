# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
import semantic.api as sapi


def test_get_paths_rejects_blank_slug() -> None:
    with pytest.raises(ConfigError):
        sapi.get_paths("   ")
