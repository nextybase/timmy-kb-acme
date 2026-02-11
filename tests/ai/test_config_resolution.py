# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.vision_config import _resolve_vision_strict_output, resolve_vision_config
from pipeline.exceptions import ConfigError


class DummySettings(SimpleNamespace):
    def get(self, path: str) -> None:
        return None

    def as_dict(self) -> dict[str, object]:
        return {"ai": {"vision": {}}}

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
    ctx = _GovernorCtx(settings=DummySettings())
    with pytest.raises(ConfigError):
        resolve_vision_config(ctx)


def test_missing_model_raises(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-assistant")
    ctx = _GovernorCtx(settings=DummySettings())
    with pytest.raises(ConfigError) as exc:
        resolve_vision_config(ctx)
    assert exc.value.code == "vision.model.missing"
    assert exc.value.component == "vision_config"


def test_model_from_settings_avoids_make(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-model")

    class SettingsWithModel(DummySettings):
        def __init__(self):
            super().__init__()
            self._map = {"vision_model": "direct-model", "ai": {"vision": {}}}

        def get(self, path: str) -> str:
            return self._map.get(path)  # type: ignore[return-value]

        def as_dict(self) -> dict[str, object]:
            return self._map

        @property
        def vision_model(self) -> str:
            return "direct-model"

    ctx = _GovernorCtx(settings=SettingsWithModel())
    config = resolve_vision_config(ctx)
    assert config.model == "direct-model"


def test_strict_output_logs_settings_load_failure(monkeypatch, caplog, tmp_path):
    caplog.set_level("ERROR", logger="ai.vision_config")

    with pytest.raises(ConfigError):
        _resolve_vision_strict_output(None, {"ai": {"vision": {}}}, tmp_path)
    errors = [rec for rec in caplog.records if "settings_load_failed" in rec.getMessage()]
    assert len(errors) == 1




def test_missing_ai_vision_section_raises(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "env-assistant")
    ctx = _GovernorCtx(settings=SimpleNamespace(as_dict=lambda: {}))
    with pytest.raises(ConfigError, match="ai\\.vision"):
        resolve_vision_config(ctx)
