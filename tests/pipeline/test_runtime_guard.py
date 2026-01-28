# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging

import pytest

from pipeline.exceptions import ConfigError
from pipeline.runtime_guard import ensure_strict_runtime


def test_ensure_strict_runtime_allows_when_env_strict() -> None:
    ensure_strict_runtime(env={"TIMMY_BETA_STRICT": "1"}, context="test.guard")


def test_ensure_strict_runtime_errors_without_strict(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    with pytest.raises(ConfigError):
        ensure_strict_runtime(env={"TIMMY_BETA_STRICT": "0"}, context="test.guard")
    assert any("pipeline.strict_runtime.precondition_failed" in rec.message for rec in caplog.records)
