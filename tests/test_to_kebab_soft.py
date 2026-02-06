# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.path_utils import to_kebab_soft


@pytest.mark.parametrize("candidate", ["!!!", "   ", "___", "///"])
def test_to_kebab_soft_returns_empty_on_unmappable(candidate: str) -> None:
    assert to_kebab_soft(candidate) == ""
