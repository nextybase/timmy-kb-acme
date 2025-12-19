# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError
from pipeline.ownership import load_ownership


def test_load_ownership_missing_file(tmp_path):
    slug = "missing"
    with pytest.raises(ConfigError) as exc:
        load_ownership(slug, tmp_path)
    assert exc.value.code == "ownership.missing"
