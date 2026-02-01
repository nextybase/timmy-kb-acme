# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.import_utils import import_from_candidates


def test_import_from_candidates_returns_first_symbol() -> None:
    sqrt = import_from_candidates(["math:sqrt"])
    assert sqrt(16) == 4


def test_import_from_candidates_tries_multiple_candidates() -> None:
    symbol = import_from_candidates(["math:missing", "math:pi"])
    assert symbol == pytest.approx(3.14159, rel=1e-5)


def test_import_from_candidates_raises_when_all_fail() -> None:
    with pytest.raises(ImportError):
        import_from_candidates(["not_a_module:missing_attr"])
