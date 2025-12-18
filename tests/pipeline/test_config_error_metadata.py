# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.exceptions import ConfigError


def test_config_error_metadata_and_str():
    exc = ConfigError(
        "vision model missing",
        code="vision.model.missing",
        component="vision_config",
        hint="set vision.model",
    )
    assert exc.code == "vision.model.missing"
    assert exc.component == "vision_config"
    assert exc.hint == "set vision.model"
    assert str(exc) == "vision model missing"


def test_config_error_chaining_preserved():
    cause = RuntimeError("boom")
    try:
        raise ConfigError("boom config", code="test.code", component="test_comp") from cause
    except ConfigError as exc:
        assert exc.__cause__ is cause
