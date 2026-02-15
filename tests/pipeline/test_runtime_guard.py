# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging

import pytest

from pipeline.exceptions import ConfigError
from pipeline.runtime_guard import ensure_strict_runtime


def test_ensure_strict_runtime_allows_when_env_strict() -> None:
    ensure_strict_runtime(env={"TIMMY_BETA_STRICT": "1"}, context="test.guard")


def test_ensure_strict_runtime_allows_when_env_missing() -> None:
    ensure_strict_runtime(env={}, context="test.guard")


def test_ensure_strict_runtime_errors_without_strict(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    with pytest.raises(ConfigError) as exc:
        ensure_strict_runtime(env={"TIMMY_BETA_STRICT": "0"}, context="test.guard")
    assert "Strict disabilitato" in str(exc.value)
    assert any("pipeline.strict_runtime.precondition_failed" in rec.message for rec in caplog.records)


def test_ensure_strict_runtime_requires_workspace_root_when_requested(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    with pytest.raises(ConfigError) as exc:
        ensure_strict_runtime(
            env={"TIMMY_BETA_STRICT": "1"},
            context="test.guard",
            require_workspace_root=True,
        )
    assert "WORKSPACE_ROOT_DIR obbligatorio" in str(exc.value)
    assert any("pipeline.workspace_root.precondition_failed" in rec.message for rec in caplog.records)


def test_ensure_strict_runtime_accepts_workspace_root_when_requested() -> None:
    ensure_strict_runtime(
        env={"TIMMY_BETA_STRICT": "1", "WORKSPACE_ROOT_DIR": "C:/tmp/output/timmy-kb-acme"},
        context="test.guard",
        require_workspace_root=True,
    )
