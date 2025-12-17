# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any

import pytest

from ai.assistant_registry import _get_from_settings, resolve_prototimmy_config
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


def test_resolve_prototimmy_config_reads_model_via_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _sample_data()

    class FakeSettings:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._data = payload

        def get(self, path: str, default: object | None = None) -> object | None:
            return None

        def as_dict(self) -> dict[str, Any]:
            return self._data

    fake = FakeSettings(data)
    # stub dell'ENV per l'assistant id
    monkeypatch.setenv("PROTOTIMMY_ID", "asst_dummy")
    cfg = resolve_prototimmy_config(fake)
    assert cfg.model == "gpt-4.1"
    assert cfg.assistant_env == "PROTOTIMMY_ID"

    # cleanup
    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)


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
