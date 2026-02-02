# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

import ai.assistant_registry as assistant_registry
from pipeline.exceptions import ConfigError


def _set_kgraph_assistant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KGRAPH_ASSISTANT_ID", "kgraph-assistant")


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


def test_prototimmy_config_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROTOTIMMY_ID", raising=False)
    settings = _fake_settings({"ai": {"prototimmy": {"model": "proto-model"}}})
    with pytest.raises(ConfigError):
        assistant_registry.resolve_prototimmy_config(settings)


def test_assistant_id_empty_env_logs(monkeypatch, caplog):
    monkeypatch.setenv("MY_ASST", "")
    with pytest.raises(ConfigError) as excinfo:
        assistant_registry._resolve_assistant_id("MY_ASST", primary_env_name="MY_ASST")
    assert excinfo.value.code == "assistant.env.empty"


def test_resolve_kgraph_config_strict_rejects_mapping(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    _set_kgraph_assistant(monkeypatch)
    settings = {"ai": {"kgraph": {"model": "nested-model"}}}
    with pytest.raises(ConfigError) as excinfo:
        assistant_registry.resolve_kgraph_config(settings)
    assert excinfo.value.code == "config.shape.invalid"


def test_resolve_kgraph_config_non_strict_accepts_mapping(monkeypatch):
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    _set_kgraph_assistant(monkeypatch)
    settings = {"ai": {"kgraph": {"model": "nested-model"}}}
    cfg = assistant_registry.resolve_kgraph_config(settings)
    assert cfg.model == "nested-model"
