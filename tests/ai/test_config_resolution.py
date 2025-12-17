# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.config import ConfigError, resolve_vision_config


class DummySettings(SimpleNamespace):
    def get(self, path: str) -> None:
        return None

    def as_dict(self) -> dict[str, object]:
        return {}

    @property
    def vision_model(self) -> str:
        return ""

    @property
    def vision_settings(self) -> SimpleNamespace:
        return SimpleNamespace(use_kb=True, strict_output=True)


class _GovernorCtx(SimpleNamespace):
    def __init__(self, settings: SimpleNamespace):
        super().__init__(settings=settings)


def test_env_var_assistant_id(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-assistant")
    monkeypatch.setattr("ai.config._resolve_model_for_vision", lambda *args, **kwargs: "stub-model")
    ctx = _GovernorCtx(settings=DummySettings())
    config = resolve_vision_config(ctx)
    assert config.assistant_id == "env-assistant"


def test_missing_assistant_env_raises(monkeypatch):
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)
    ctx = _GovernorCtx(settings=DummySettings())
    with pytest.raises(ConfigError):
        resolve_vision_config(ctx)


def test_model_from_assistant_called_only_when_needed(monkeypatch):
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-model")

    called = {"make": 0, "retrieve": 0}

    class FakeAssistant(SimpleNamespace):
        model = "assistant-model"

    class FakeClient:
        assistants = SimpleNamespace(retrieve=lambda identifier: _count(identifier))

    def _count(identifier: str) -> SimpleNamespace:
        called["retrieve"] += 1
        return FakeAssistant()

    def fake_make():
        called["make"] += 1
        return FakeClient()

    monkeypatch.setattr("ai.config.make_openai_client", fake_make)
    ctx = _GovernorCtx(settings=DummySettings())
    config = resolve_vision_config(ctx)
    assert config.model == "assistant-model"
    assert called["make"] == 1
    assert called["retrieve"] == 1


def test_model_from_settings_avoids_make(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-model")

    class SettingsWithModel(DummySettings):
        def __init__(self):
            super().__init__()
            self._map = {"vision_model": "direct-model"}

        def get(self, path: str) -> str:
            return self._map.get(path)  # type: ignore[return-value]

        def as_dict(self) -> dict[str, object]:
            return self._map

        @property
        def vision_model(self) -> str:
            return "direct-model"

    def fake_make():
        raise AssertionError("make_openai_client should not be called when model present")

    monkeypatch.setattr("ai.config.make_openai_client", fake_make)
    ctx = _GovernorCtx(settings=SettingsWithModel())
    config = resolve_vision_config(ctx)
    assert config.model == "direct-model"
