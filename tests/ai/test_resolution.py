# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

import ai.resolution as resolution
from pipeline.exceptions import ConfigError


def test_resolve_assistant_env_prefers_settings_over_payload() -> None:
    assert resolution.resolve_assistant_env("SETTINGS_ENV", "payload_env", "DEFAULT_ENV") == "SETTINGS_ENV"
    assert resolution.resolve_assistant_env(None, "payload_env", "DEFAULT_ENV") == "payload_env"
    assert resolution.resolve_assistant_env(None, None, "DEFAULT_ENV") == "DEFAULT_ENV"


def test_resolve_assistant_id_uses_fallback_and_errors() -> None:
    assert resolution.resolve_assistant_id("primary", "fallback", "PRIMARY_NAME") == "primary"
    assert resolution.resolve_assistant_id(None, "fallback_value", "PRIMARY_NAME") == "fallback_value"
    with pytest.raises(ConfigError) as exc:
        resolution.resolve_assistant_id(None, None, "PRIMARY_NAME")
    assert "PRIMARY_NAME" in str(exc.value)


def test_resolve_model_precedence() -> None:
    assert (
        resolution.resolve_model_precedence("override", "settings", "payload", "assistant", error_message="fail")
        == "override"
    )
    assert (
        resolution.resolve_model_precedence("", "settings", "payload", "assistant", error_message="fail") == "settings"
    )
    assert resolution.resolve_model_precedence("", "", "payload", "assistant", error_message="fail") == "payload"
    assert resolution.resolve_model_precedence("", "", "", "assistant", error_message="fail") == "assistant"
    with pytest.raises(ConfigError):
        resolution.resolve_model_precedence("", "", "", "", error_message="fail")


def test_resolve_boolean_flag_precedence() -> None:
    assert resolution.resolve_boolean_flag(True, False, False, default=False) is True
    assert resolution.resolve_boolean_flag(None, True, False, default=False) is True
    assert resolution.resolve_boolean_flag(None, None, True, default=False) is True
    assert resolution.resolve_boolean_flag(None, None, None, default=True) is True
