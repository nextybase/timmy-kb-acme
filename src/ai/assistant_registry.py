# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from typing import Optional

import pipeline.env_utils as env_utils
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings

from .resolution import resolve_assistant_env, resolve_assistant_id, resolve_boolean_flag
from .types import AssistantConfig

LOGGER = get_structured_logger("ai.assistant_registry")


def _optional_env(name: str) -> Optional[str]:
    raw_env_value = os.environ.get(name)
    if raw_env_value is not None and not str(raw_env_value).strip():
        raise ConfigError(
            f"Variabile ambiente vuota: {name}.",
            code="assistant.env.empty",
            component="assistant_registry",
            env=name,
        )
    try:
        value = env_utils.get_env_var(name)
    except KeyError:
        return None
    except Exception as exc:
        raise ConfigError(
            f"Lettura variabile ambiente fallita: {name}.",
            code="assistant.env.read_failed",
            component="assistant_registry",
            env=name,
        ) from exc
    return value.strip() if isinstance(value, str) else None


def _get_from_settings(settings: object, path: str, default: object = None) -> object:
    if isinstance(settings, Settings):
        try:
            return settings.get_value(path, default=default)
        except KeyError:
            return default
    # Contratto deterministico: il core accetta solo Settings tipizzato.
    raise ConfigError(
        "Settings non conforme: atteso pipeline.settings.Settings.",
        code="config.shape.invalid",
        component="assistant_registry",
        path=path,
    )


def _resolve_assistant_env_name(settings: Settings, path: str, default_env: str) -> str:
    settings_value = _get_from_settings(settings, path)
    settings_candidate = settings_value if isinstance(settings_value, str) else None
    return resolve_assistant_env(settings_candidate, None, default_env)


def _resolve_assistant_id(env_name: str, *, primary_env_name: str) -> str:
    primary_value = _optional_env(env_name)
    # Strict guard: niente downgrade a None.
    # Copre anche eventuali ritorni anomali da env_utils.get_env_var().
    if primary_value is not None and not str(primary_value).strip():
        raise ConfigError(
            f"Variabile ambiente vuota: {env_name}.",
            code="assistant.env.empty",
            component="assistant_registry",
            env=env_name,
        )
    return resolve_assistant_id(
        primary_value,
        primary_env_name,
    )


def _resolve_model(settings: Settings, path: str, *, default: Optional[str] = None) -> str:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if default and default.strip():
        return default.strip()
    raise ConfigError(
        f"Modello non configurato per {path}.",
        code="assistant.model.missing",
        component="assistant_registry",
    )


def _resolve_bool(settings: Settings, path: str, default: Optional[bool]) -> Optional[bool]:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, bool):
        return candidate
    return default


def _build_assistant_config(
    *,
    settings: Settings,
    model_path: str,
    assistant_env_path: str,
    default_env: str,
    use_kb_path: Optional[str] = None,
    strict_output_path: Optional[str] = None,
    default_use_kb: Optional[bool] = None,
    default_strict_output: Optional[bool] = None,
    model_default: Optional[str] = None,
) -> AssistantConfig:
    assistant_env = _resolve_assistant_env_name(settings, assistant_env_path, default_env)
    assistant_id = _resolve_assistant_id(assistant_env, primary_env_name=assistant_env)
    model = _resolve_model(settings, model_path, default=model_default)
    use_kb = (
        resolve_boolean_flag(None, _resolve_bool(settings, use_kb_path, default_use_kb), None, default=True)
        if use_kb_path
        else None
    )
    strict_output = (
        resolve_boolean_flag(
            None, _resolve_bool(settings, strict_output_path, default_strict_output), None, default=True
        )
        if strict_output_path
        else None
    )
    return AssistantConfig(
        model=model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=use_kb,
        strict_output=strict_output,
    )


def resolve_kgraph_config(settings: Settings, assistant_env_override: Optional[str] = None) -> AssistantConfig:
    assistant_env_path = "ai.kgraph.assistant_id_env"
    default_env = "KGRAPH_ASSISTANT_ID"
    if assistant_env_override:
        assistant_env = resolve_assistant_env(assistant_env_override, None, default_env)
        assistant_id = _resolve_assistant_id(assistant_env, primary_env_name=assistant_env)
        model = _resolve_model(settings, "ai.kgraph.model")
        return AssistantConfig(model=model, assistant_id=assistant_id, assistant_env=assistant_env)
    return _build_assistant_config(
        settings=settings,
        model_path="ai.kgraph.model",
        assistant_env_path=assistant_env_path,
        default_env=default_env,
    )


def resolve_prototimmy_config(settings: Settings) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.prototimmy.model",
        assistant_env_path="ai.prototimmy.assistant_id_env",
        default_env="PROTOTIMMY_ID",
        use_kb_path="ai.prototimmy.use_kb",
        default_use_kb=True,
    )


def resolve_planner_config(settings: Settings) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.planner_assistant.model",
        assistant_env_path="ai.planner_assistant.assistant_id_env",
        default_env="PLANNER_ASSISTANT_ID",
        use_kb_path="ai.planner_assistant.use_kb",
        default_use_kb=True,
    )


def resolve_ocp_executor_config(settings: Settings) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.ocp_executor.model",
        assistant_env_path="ai.ocp_executor.assistant_id_env",
        default_env="OCP_EXECUTOR_ASSISTANT_ID",
        use_kb_path="ai.ocp_executor.use_kb",
        default_use_kb=True,
    )


def resolve_audit_assistant_config(settings: Settings) -> AssistantConfig:
    assistant_env = _resolve_assistant_env_name(settings, "ai.audit_assistant.assistant_id_env", "AUDIT_ASSISTANT_ID")
    assistant_id = _resolve_assistant_id(assistant_env, primary_env_name=assistant_env)
    model = _resolve_model(settings, "ai.audit_assistant.model")
    return AssistantConfig(
        model=model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=False,
        strict_output=None,
    )
