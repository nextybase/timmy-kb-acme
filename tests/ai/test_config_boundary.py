# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
from typing import Callable

import pytest

import ai.vision_config as config
from ai.assistant_registry import (
    resolve_audit_assistant_config,
    resolve_kgraph_config,
    resolve_ocp_executor_config,
    resolve_planner_config,
    resolve_prototimmy_config,
)
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings


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


def _make_settings(payload: dict[str, object]) -> Settings:
    return Settings(config_path=Path("config/config.yaml"), data=payload)


def test_resolve_prototimmy_config_missing_assistant_id_raises(monkeypatch):
    settings = _make_settings({"ai": {"prototimmy": {"model": "proto-model"}}})
    monkeypatch.setattr("pipeline.env_utils.get_env_var", _missing_env)
    with pytest.raises(ConfigError) as exc:
        resolve_prototimmy_config(settings)
    assert "PROTOTIMMY_ID" in str(exc.value)


def test_resolve_kgraph_config_requires_model(monkeypatch):
    settings = _make_settings({"ai": {"kgraph": {"model": "kgraph-model"}}})

    def fake_env(name: str, required: bool = False) -> str:
        if name == "KGRAPH_ASSISTANT_ID":
            return "kgraph-assistant"
        raise KeyError(name)

    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)

    result = resolve_kgraph_config(settings)
    assert result.assistant_id == "kgraph-assistant"
    assert result.model == "kgraph-model"


def test_resolve_kgraph_config_prefers_nested_model(monkeypatch):
    settings = _make_settings(
        {
            "ai": {"kgraph": {"model": "nested-model", "assistant_id_env": "KGRAPH_ASSISTANT_ID"}},
            "ai.kgraph.model": "flat-model",
        }
    )

    def fake_env(name: str, required: bool = False) -> str:
        if name == "KGRAPH_ASSISTANT_ID":
            return "kgraph-assistant"
        raise KeyError(name)

    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)
    result = resolve_kgraph_config(settings)
    assert result.model == "nested-model"


def test_assistant_env_precedence_settings(monkeypatch):
    class _StubSettings:
        vision_assistant_env = "settings-env"

    payload = {"ai": {"vision": {"assistant_id_env": "payload-env"}}}
    monkeypatch.setattr(config, "Settings", _StubSettings)
    result = config._resolve_assistant_env(_StubSettings(), payload, default_env="DEFAULT_ENV")
    assert result == "settings-env"


def test_vision_assistant_env_payload_over_default():
    payload = {"ai": {"vision": {"assistant_id_env": "PAYLOAD_ENV"}}}
    env_name = config._resolve_assistant_env(None, payload, default_env="DEFAULT_ENV")
    assert env_name == "PAYLOAD_ENV"


def test_ai_section_assistant_env_payload_precedence():
    settings = _make_settings({"ai": {"prototimmy": {"assistant_id_env": "PROTO_PAYLOAD_ENV"}}})
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
            resolve_prototimmy_config,
            "PROTOTIMMY_ID",
            lambda ctx: resolve_prototimmy_config(ctx.settings),
        ),
        (
            resolve_planner_config,
            "PLANNER_ASSISTANT_ID",
            lambda ctx: resolve_planner_config(ctx.settings),
        ),
        (
            resolve_ocp_executor_config,
            "OCP_EXECUTOR_ASSISTANT_ID",
            lambda ctx: resolve_ocp_executor_config(ctx.settings),
        ),
        (resolve_kgraph_config, "KGRAPH_ASSISTANT_ID", lambda ctx: resolve_kgraph_config(ctx.settings)),
        (
            resolve_audit_assistant_config,
            "AUDIT_ASSISTANT_ID",
            lambda ctx: resolve_audit_assistant_config(ctx.settings),
        ),
    ),
)
def test_resolvers_missing_env_raise(monkeypatch, resolver, env_name, resolver_call):
    ctx = _DummyCtx(settings={})
    fake_env = _fake_env_factory({})
    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)
    if env_name in {
        "PROTOTIMMY_ID",
        "PLANNER_ASSISTANT_ID",
        "OCP_EXECUTOR_ASSISTANT_ID",
        "AUDIT_ASSISTANT_ID",
        "OBNEXT_ASSISTANT_ID",
        "KGRAPH_ASSISTANT_ID",
    }:
        if env_name == "OBNEXT_ASSISTANT_ID":
            ctx.settings = _make_settings({"ai": {"vision": {"assistant_id_env": env_name, "model": "dummy-model"}}})
        else:
            section = {
                "PROTOTIMMY_ID": "prototimmy",
                "PLANNER_ASSISTANT_ID": "planner_assistant",
                "OCP_EXECUTOR_ASSISTANT_ID": "ocp_executor",
                "AUDIT_ASSISTANT_ID": "audit_assistant",
                "KGRAPH_ASSISTANT_ID": "kgraph",
            }[env_name]
            ctx.settings = _make_settings({"ai": {section: {"model": "dummy-model", "assistant_id_env": env_name}}})
    with pytest.raises(ConfigError) as exc:
        resolver_call(ctx)
    assert env_name in str(exc.value)


@pytest.mark.parametrize(
    "resolver, model_path, env_name",
    (
        (resolve_prototimmy_config, "ai.prototimmy.model", "PROTOTIMMY_ID"),
        (resolve_planner_config, "ai.planner_assistant.model", "PLANNER_ASSISTANT_ID"),
        (resolve_ocp_executor_config, "ai.ocp_executor.model", "OCP_EXECUTOR_ASSISTANT_ID"),
    ),
)
def test_non_assistant_resolvers_require_model(monkeypatch, resolver, model_path, env_name):
    settings = _make_settings({"ai": {model_path.split(".")[1]: {"model": "", "assistant_id_env": env_name}}})
    fake_env = _fake_env_factory({env_name: f"{env_name.lower()}-assistant"})
    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)
    with pytest.raises(ConfigError) as exc:
        resolver(settings)
    assert model_path in str(exc.value)


def test_resolve_audit_assistant_success(monkeypatch):
    fake_env = _fake_env_factory({"AUDIT_ASSISTANT_ID": "audit-assistant"})
    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)
    result = resolve_audit_assistant_config(_make_settings({"ai": {"audit_assistant": {"model": "audit-model"}}}))
    assert result.assistant_id == "audit-assistant"
    assert result.model == "audit-model"
    assert result.use_kb is False


def test_resolve_audit_assistant_missing_env(monkeypatch):
    monkeypatch.setattr("pipeline.env_utils.get_env_var", _missing_env)
    with pytest.raises(ConfigError) as exc:
        resolve_audit_assistant_config(_make_settings({"ai": {"audit_assistant": {"model": "audit-model"}}}))
    assert "AUDIT_ASSISTANT_ID" in str(exc.value)


def test_resolve_audit_assistant_missing_model(monkeypatch):
    fake_env = _fake_env_factory({"AUDIT_ASSISTANT_ID": "audit-assistant"})
    monkeypatch.setattr("pipeline.env_utils.get_env_var", fake_env)
    with pytest.raises(ConfigError) as exc:
        resolve_audit_assistant_config(_make_settings({"ai": {"audit_assistant": {"model": ""}}}))
    assert "ai.audit_assistant.model" in str(exc.value)


def test_legacy_root_vision_rejected(caplog):
    ctx = _DummyCtx(settings={"vision": {"assistant_id_env": "OBNEXT_ASSISTANT_ID", "model": "m"}})
    caplog.set_level("ERROR", logger="ai.vision_config")
    with pytest.raises(ConfigError, match="ai\\.vision"):
        config.resolve_vision_config(ctx)
    assert any(rec.message == "ai.vision_config.legacy_root_vision" for rec in caplog.records)


def test_vision_optional_env_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISION_MISSING_ENV", raising=False)

    def _missing(name: str) -> str:
        raise KeyError(name)

    monkeypatch.setattr("ai.vision_config.env_utils.get_env_var", _missing)
    assert config._optional_env("VISION_MISSING_ENV") is None


def test_vision_optional_env_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_EMPTY_ENV", "  ")
    with pytest.raises(ConfigError) as excinfo:
        config._optional_env("VISION_EMPTY_ENV")
    assert excinfo.value.code == "assistant.env.empty"


def test_vision_optional_env_read_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_BROKEN_ENV", "ok")

    def _raise_runtime(name: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("ai.vision_config.env_utils.get_env_var", _raise_runtime)
    with pytest.raises(ConfigError) as excinfo:
        config._optional_env("VISION_BROKEN_ENV")
    assert excinfo.value.code == "assistant.env.read_failed"


@pytest.mark.parametrize("value", ("bad", 0), ids=("invalid_type", "non_positive"))
def test_resolve_vision_retention_days_invalid_values(value) -> None:
    ctx = _DummyCtx(settings={"ai": {"vision": {"snapshot_retention_days": value}}})
    with pytest.raises(ConfigError) as excinfo:
        config.resolve_vision_retention_days(ctx)
    assert excinfo.value.code == "vision.retention.invalid"


def test_resolve_vision_retention_days_missing() -> None:
    ctx = _DummyCtx(settings={"ai": {"vision": {}}})
    with pytest.raises(ConfigError) as excinfo:
        config.resolve_vision_retention_days(ctx)
    assert excinfo.value.code == "vision.retention.missing"
