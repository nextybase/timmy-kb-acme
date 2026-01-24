# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from pipeline.beta_flags import is_beta_strict


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_is_beta_strict_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", value)
    assert is_beta_strict() is True


@pytest.mark.parametrize("value", ["", "0", "false"])
def test_is_beta_strict_falsy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", value)
    assert is_beta_strict() is False


def test_is_beta_strict_accepts_mapping() -> None:
    assert is_beta_strict({"TIMMY_BETA_STRICT": "1"}) is True
    assert is_beta_strict({"TIMMY_BETA_STRICT": "false"}) is False
