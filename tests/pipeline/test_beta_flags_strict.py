# SPDX-License-Identifier: GPL-3.0-or-later
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
        ("", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
    ),
)
def test_is_beta_strict_values(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", value)
    assert is_beta_strict() is expected


def test_is_beta_strict_defaults_to_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIMMY_BETA_STRICT", raising=False)
    assert is_beta_strict() is True


def test_is_beta_strict_accepts_mapping() -> None:
    assert is_beta_strict({"TIMMY_BETA_STRICT": "1"}) is True
    assert is_beta_strict({"TIMMY_BETA_STRICT": "false"}) is False
