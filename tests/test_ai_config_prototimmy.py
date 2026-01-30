# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any

import pytest

from ai.assistant_registry import _get_from_settings, _optional_env, resolve_prototimmy_config
from pipeline.exceptions import ConfigError


def _sample_data() -> dict[str, Any]:
    return {
        "ai": {
            "prototimmy": {
                "model": "gpt-4.1",
                "assistant_id_env": "PROTOTIMMY_ID",
                "use_kb": True,
            }
        }
    }


def test_get_from_settings_reads_nested_model_from_mapping() -> None:
    data = _sample_data()
    value = _get_from_settings(data, "ai.prototimmy.model", default=None)
    assert value == "gpt-4.1"


def test_get_from_settings_reads_nested_model_from_settings_like_object(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _sample_data()

    class FakeSettings:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._data = payload

        def get(self, path: str, default: object | None = None) -> object | None:
            # Simula il caso problematico: sempre None
            return None

        def as_dict(self) -> dict[str, Any]:
            return self._data

    fake = FakeSettings(data)
    value = _get_from_settings(fake, "ai.prototimmy.model", default=None)
    assert value == "gpt-4.1"


def test_get_from_settings_raises_on_settings_get_error() -> None:
    class FakeSettings:
        def get(self, path: str, default: object | None = None) -> object | None:
            raise RuntimeError("boom")

    with pytest.raises(ConfigError) as excinfo:
        _get_from_settings(FakeSettings(), "ai.prototimmy.model", default=None)
    assert excinfo.value.code == "config.read.failed"


def test_get_from_settings_raises_on_as_dict_error() -> None:
    class FakeSettings:
        def get(self, path: str, default: object | None = None) -> object | None:
            return None

        def as_dict(self) -> dict[str, Any]:
            raise RuntimeError("boom")

    with pytest.raises(ConfigError) as excinfo:
        _get_from_settings(FakeSettings(), "ai.prototimmy.model", default=None)
    assert excinfo.value.code == "config.read.failed"


def test_get_from_settings_raises_on_non_mapping() -> None:
    class FakeSettings:
        def get(self, path: str, default: object | None = None) -> object | None:
            return None

    with pytest.raises(ConfigError) as excinfo:
        _get_from_settings(FakeSettings(), "ai.prototimmy.model", default=None)
    assert excinfo.value.code == "config.read.failed"


def test_get_from_settings_strict_rejects_non_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSettings:
        def get(self, path: str, default: object | None = None) -> object | None:
            return None

        def as_dict(self) -> dict[str, Any]:
            return _sample_data()

    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    with pytest.raises(ConfigError) as excinfo:
        _get_from_settings(FakeSettings(), "ai.prototimmy.model", default=None)
    assert excinfo.value.code == "config.shape.invalid"


def test_resolve_prototimmy_config_raises_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {"ai": {"prototimmy": {"assistant_id_env": "PROTOTIMMY_ID"}}}

    class FakeSettings:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._data = payload

        def get(self, path: str, default: object | None = None) -> object | None:
            return None

        def as_dict(self) -> dict[str, Any]:
            return self._data

    fake = FakeSettings(data)
    monkeypatch.setenv("PROTOTIMMY_ID", "asst_dummy")

    with pytest.raises(ConfigError):
        resolve_prototimmy_config(fake)

    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)


def test_optional_env_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_ENV", raising=False)

    def _raise_key_error(name: str) -> str:
        raise KeyError(name)

    monkeypatch.setattr("ai.assistant_registry.env_utils.get_env_var", _raise_key_error)
    assert _optional_env("MISSING_ENV") is None


def test_optional_env_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPTY_ENV", "  ")
    with pytest.raises(ConfigError) as excinfo:
        _optional_env("EMPTY_ENV")
    assert excinfo.value.code == "assistant.env.empty"


def test_optional_env_read_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROKEN_ENV", "ok")

    def _raise_runtime_error(name: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("ai.assistant_registry.env_utils.get_env_var", _raise_runtime_error)
    with pytest.raises(ConfigError) as excinfo:
        _optional_env("BROKEN_ENV")
    assert excinfo.value.code == "assistant.env.read_failed"
