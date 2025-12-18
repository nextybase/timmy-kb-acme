# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

import ai.assistant_registry as assistant_registry
from pipeline.exceptions import ConfigError


def _fake_settings(mapping: dict[str, object]) -> dict[str, object]:
    return mapping


def test_prototimmy_config_uses_standard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTOTIMMY_ID", "proto-asst")
    settings = _fake_settings({"ai": {"prototimmy": {"model": "proto-model"}}})
    cfg = assistant_registry.resolve_prototimmy_config(settings)
    assert cfg.assistant_env == "PROTOTIMMY_ID"
    assert cfg.assistant_id == "proto-asst"
    assert cfg.model == "proto-model"


def test_prototimmy_config_uses_custom_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_ASSISTANT_ID", "custom-asst")
    settings = _fake_settings(
        {
            "ai": {
                "prototimmy": {
                    "model": "proto-model",
                    "assistant_id_env": "CUSTOM_ASSISTANT_ID",
                }
            }
        }
    )
    cfg = assistant_registry.resolve_prototimmy_config(settings)
    assert cfg.assistant_env == "CUSTOM_ASSISTANT_ID"
    assert cfg.assistant_id == "custom-asst"


def test_prototimmy_config_falls_back_to_assistant_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)
    monkeypatch.setenv("ASSISTANT_ID", "fallback-asst")
    settings = _fake_settings({"ai": {"prototimmy": {"model": "proto-model"}}})
    cfg = assistant_registry.resolve_prototimmy_config(settings)
    assert cfg.assistant_id == "fallback-asst"


def test_assistant_model_lookup_failure_logs(monkeypatch: pytest.MonkeyPatch, caplog):
    class BadAssistants:
        def retrieve(self, _: str) -> None:
            raise RuntimeError("boom")

    client = type("C", (), {"assistants": BadAssistants()})()
    caplog.set_level("WARNING", logger="ai.assistant_registry")
    result = assistant_registry._resolve_model_from_assistant(client, "broken-asst")
    assert result is None
    assert any("assistant_model_lookup_failed" in rec.getMessage() for rec in caplog.records)


def test_assistant_id_empty_env_logs(monkeypatch, caplog):
    monkeypatch.setenv("MY_ASST", "")
    monkeypatch.setenv("ASSISTANT_ID", "")
    caplog.set_level("WARNING", logger="ai.assistant_registry")
    with pytest.raises(ConfigError):
        assistant_registry._resolve_assistant_id(
            "MY_ASST", primary_env_name="MY_ASST", fallback_env_name="ASSISTANT_ID"
        )
    assert any("env_var_empty" in rec.getMessage() for rec in caplog.records)
