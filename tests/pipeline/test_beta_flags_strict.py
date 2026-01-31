# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from pipeline.beta_flags import is_beta_strict


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("", False),
        ("0", False),
        ("false", False),
    ),
)
def test_is_beta_strict_values(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", value)
    assert is_beta_strict() is expected


def test_is_beta_strict_accepts_mapping() -> None:
    assert is_beta_strict({"TIMMY_BETA_STRICT": "1"}) is True
    assert is_beta_strict({"TIMMY_BETA_STRICT": "false"}) is False
