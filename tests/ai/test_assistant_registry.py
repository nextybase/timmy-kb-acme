# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from ai import assistant_registry


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
