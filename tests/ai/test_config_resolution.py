# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.vision_config import _load_settings_cached, _resolve_vision_strict_output, resolve_vision_config
from pipeline.exceptions import ConfigError


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
    monkeypatch.setattr("ai.vision_config._resolve_model_for_vision", lambda *args, **kwargs: "stub-model")
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

    monkeypatch.setattr("ai.vision_config.make_openai_client", fake_make)
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

    monkeypatch.setattr("ai.vision_config.make_openai_client", fake_make)
    ctx = _GovernorCtx(settings=SettingsWithModel())
    config = resolve_vision_config(ctx)
    assert config.model == "direct-model"


def test_resolve_vision_config_client_failure(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-assistant")

    def fail_make():
        raise ConfigError("missing OPENAI_API_KEY")

    monkeypatch.setattr("ai.vision_config.make_openai_client", fail_make)
    ctx = _GovernorCtx(settings=DummySettings())
    with pytest.raises(ConfigError) as exc:
        resolve_vision_config(ctx)
    assert "Vision model lookup failed" in str(exc.value)
    assert exc.value.code == "vision.client.config.invalid"
    assert exc.value.component == "vision_config"


def test_strict_output_logs_settings_load_failure(monkeypatch, caplog, tmp_path):
    caplog.set_level("WARNING", logger="ai.vision_config")

    monkeypatch.setattr(
        "ai.vision_config.Settings.load",
        lambda base_dir: (_ for _ in ()).throw(RuntimeError("can not read settings")),
    )

    result = _resolve_vision_strict_output(None, {}, tmp_path)
    assert result is True
    assert any("settings_load_failed" in rec.getMessage() for rec in caplog.records)


def test_strict_output_load_cached(monkeypatch, caplog, tmp_path):
    caplog.set_level("WARNING", logger="ai.vision_config")
    calls = 0

    def fake_load(base_dir):
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    monkeypatch.setattr("ai.vision_config.Settings.load", fake_load)
    _load_settings_cached.cache_clear()

    _resolve_vision_strict_output(None, {}, tmp_path)
    _resolve_vision_strict_output(None, {}, tmp_path)

    assert calls == 1
    warnings = [rec for rec in caplog.records if "settings_load_failed" in rec.getMessage()]
    assert len(warnings) == 1


def test_resolve_vision_config_assistant_lookup_failure(monkeypatch, caplog):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-assistant")
    caplog.set_level("WARNING", logger="ai.assistant_registry")

    class _FailingAssistants:
        def retrieve(self, _: str):
            raise TimeoutError("timeout")

    client = type("C", (), {"assistants": _FailingAssistants()})()
    monkeypatch.setattr("ai.vision_config.make_openai_client", lambda: client)

    ctx = _GovernorCtx(settings=DummySettings())
    with pytest.raises(ConfigError) as exc:
        resolve_vision_config(ctx)

    assert "Modello Vision non configurato" in str(exc.value)
    assert any("assistant_model_lookup_failed" in rec.getMessage() for rec in caplog.records)
    assert exc.value.code == "vision.model.missing"
    assert exc.value.component == "vision_config"
