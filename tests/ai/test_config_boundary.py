# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace
from typing import Callable

import pytest

from ai import config
from pipeline.exceptions import ConfigError


class _DummyCtx:
    def __init__(self, settings=None, base_dir=None):
        self.settings = settings
        self.base_dir = base_dir


def _missing_env(name: str, required: bool = False) -> str:
    raise KeyError(name)


def _fake_env_factory(mapping: dict[str, str]) -> Callable[[str, bool], str]:
    def _fake_env(name: str, required: bool = False) -> str:
        if name in mapping:
            return mapping[name]
        raise KeyError(name)

    return _fake_env


def test_resolve_vision_config_prefers_env(monkeypatch):
    ctx = _DummyCtx(settings={"vision": {"assistant_id_env": "VISION_OVERRIDE_ENV", "model": "config-model"}})

    def fake_env(name: str, required: bool = False) -> str:
        if name == "VISION_OVERRIDE_ENV":
            return "env-vision"
        raise KeyError(name)

    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    result = config.resolve_vision_config(ctx)
    assert result.assistant_id == "env-vision"
    assert result.model == "config-model"


def test_resolve_prototimmy_config_missing_assistant_id_raises(monkeypatch):
    settings = {"ai": {"prototimmy": {"model": "proto-model"}}}
    monkeypatch.setattr("ai.config.get_env_var", _missing_env)
    with pytest.raises(ConfigError) as exc:
        config.resolve_prototimmy_config(settings)
    assert "PROTOTIMMY_ID" in str(exc.value)


def test_resolve_kgraph_config_falls_back_to_assistant_model(monkeypatch):
    settings = {}

    def fake_env(name: str, required: bool = False) -> str:
        if name == "KGRAPH_ASSISTANT_ID":
            return "kgraph-assistant"
        raise KeyError(name)

    class _DummyAssistants:
        def retrieve(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(model="assistant-model")

    class _DummyClient:
        assistants = _DummyAssistants()

    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    monkeypatch.setattr("ai.config.make_openai_client", lambda: _DummyClient())

    result = config.resolve_kgraph_config(settings)
    assert result.assistant_id == "kgraph-assistant"
    assert result.model == "assistant-model"


def test_resolve_vision_config_fallbacks_to_assistant_model(monkeypatch):
    ctx = _DummyCtx(settings={})

    fake_env = _fake_env_factory({"OBNEXT_ASSISTANT_ID": "vision-assistant"})

    class _DummyAssistants:
        def retrieve(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(model="vision-assistant-model")

    class _DummyClient:
        assistants = _DummyAssistants()

    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    monkeypatch.setattr("ai.config.make_openai_client", lambda: _DummyClient())

    result = config.resolve_vision_config(ctx)
    assert result.assistant_id == "vision-assistant"
    assert result.model == "vision-assistant-model"


def test_assistant_env_precedence_settings(monkeypatch):
    class _StubSettings:
        vision_assistant_env = "settings-env"

    payload = {"vision": {"assistant_id_env": "payload-env"}}
    monkeypatch.setattr(config, "Settings", _StubSettings)
    result = config._resolve_assistant_env(_StubSettings(), payload, default_env="DEFAULT_ENV")
    assert result == "settings-env"


def test_vision_assistant_env_payload_over_default():
    payload = {"vision": {"assistant_id_env": "PAYLOAD_ENV"}}
    env_name = config._resolve_assistant_env(None, payload, default_env="DEFAULT_ENV")
    assert env_name == "PAYLOAD_ENV"


def test_ai_section_assistant_env_payload_precedence():
    settings = {"ai": {"prototimmy": {"assistant_id_env": "PROTO_PAYLOAD_ENV"}}}
    env_name = config._resolve_assistant_env_generic(
        settings,
        "ai.prototimmy.assistant_id_env",
        "DEFAULT_ENV",
    )
    assert env_name == "PROTO_PAYLOAD_ENV"


@pytest.mark.parametrize(
    "resolver, env_name, resolver_call",
    (
        (config.resolve_vision_config, "OBNEXT_ASSISTANT_ID", lambda ctx: config.resolve_vision_config(ctx)),
        (
            config.resolve_prototimmy_config,
            "PROTOTIMMY_ID",
            lambda ctx: config.resolve_prototimmy_config(ctx.settings),
        ),
        (
            config.resolve_planner_config,
            "PLANNER_ASSISTANT_ID",
            lambda ctx: config.resolve_planner_config(ctx.settings),
        ),
        (
            config.resolve_ocp_executor_config,
            "OCP_EXECUTOR_ASSISTANT_ID",
            lambda ctx: config.resolve_ocp_executor_config(ctx.settings),
        ),
        (config.resolve_kgraph_config, "KGRAPH_ASSISTANT_ID", lambda ctx: config.resolve_kgraph_config(ctx)),
        (
            config.resolve_audit_assistant_config,
            "AUDIT_ASSISTANT_ID",
            lambda ctx: config.resolve_audit_assistant_config(ctx.settings),
        ),
    ),
)
def test_resolvers_missing_env_raise(monkeypatch, resolver, env_name, resolver_call):
    ctx = _DummyCtx(settings={})
    fake_env = _fake_env_factory({})
    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    if env_name in {
        "PROTOTIMMY_ID",
        "PLANNER_ASSISTANT_ID",
        "OCP_EXECUTOR_ASSISTANT_ID",
        "AUDIT_ASSISTANT_ID",
    }:
        section = {
            "PROTOTIMMY_ID": "prototimmy",
            "PLANNER_ASSISTANT_ID": "planner_assistant",
            "OCP_EXECUTOR_ASSISTANT_ID": "ocp_executor",
            "AUDIT_ASSISTANT_ID": "audit_assistant",
        }[env_name]
        ctx.settings = {"ai": {section: {"model": "dummy-model", "assistant_id_env": env_name}}}
    with pytest.raises(ConfigError) as exc:
        resolver_call(ctx)
    assert env_name in str(exc.value)


@pytest.mark.parametrize(
    "resolver, model_path, env_name",
    (
        (config.resolve_prototimmy_config, "ai.prototimmy.model", "PROTOTIMMY_ID"),
        (config.resolve_planner_config, "ai.planner_assistant.model", "PLANNER_ASSISTANT_ID"),
        (config.resolve_ocp_executor_config, "ai.ocp_executor.model", "OCP_EXECUTOR_ASSISTANT_ID"),
    ),
)
def test_non_assistant_resolvers_require_model(monkeypatch, resolver, model_path, env_name):
    settings = {"ai": {model_path.split(".")[1]: {"model": "", "assistant_id_env": env_name}}}
    fake_env = _fake_env_factory({env_name: f"{env_name.lower()}-assistant"})
    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    with pytest.raises(ConfigError) as exc:
        resolver(settings)
    assert model_path in str(exc.value)


def test_resolve_audit_assistant_success(monkeypatch):
    fake_env = _fake_env_factory({"AUDIT_ASSISTANT_ID": "audit-assistant"})
    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    result = config.resolve_audit_assistant_config({"ai": {"audit_assistant": {"model": "audit-model"}}})
    assert result.assistant_id == "audit-assistant"
    assert result.model == "audit-model"
    assert result.use_kb is False


def test_resolve_audit_assistant_missing_env(monkeypatch):
    monkeypatch.setattr("ai.config.get_env_var", _missing_env)
    with pytest.raises(ConfigError) as exc:
        config.resolve_audit_assistant_config({"ai": {"audit_assistant": {"model": "audit-model"}}})
    assert "AUDIT_ASSISTANT_ID" in str(exc.value)


def test_resolve_audit_assistant_missing_model(monkeypatch):
    fake_env = _fake_env_factory({"AUDIT_ASSISTANT_ID": "audit-assistant"})
    monkeypatch.setattr("ai.config.get_env_var", fake_env)
    with pytest.raises(ConfigError) as exc:
        config.resolve_audit_assistant_config({"ai": {"audit_assistant": {"model": ""}}})
    assert "ai.audit_assistant.model" in str(exc.value)
