# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.env_utils import is_beta_strict


def test_is_beta_strict_truthy_values() -> None:
    env = {
        "TIMMY_BETA_STRICT": "1",
    }
    assert is_beta_strict(env) is True
    env["TIMMY_BETA_STRICT"] = "true"
    assert is_beta_strict(env) is True
    env["TIMMY_BETA_STRICT"] = "yes"
    assert is_beta_strict(env) is True
    env["TIMMY_BETA_STRICT"] = "on"
    assert is_beta_strict(env) is True


def test_is_beta_strict_falsy_values() -> None:
    env = {
        "TIMMY_BETA_STRICT": "",
    }
    assert is_beta_strict(env) is False
    env["TIMMY_BETA_STRICT"] = "0"
    assert is_beta_strict(env) is False
    env["TIMMY_BETA_STRICT"] = "false"
    assert is_beta_strict(env) is False
