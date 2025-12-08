# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings

from .client_factory import make_openai_client
from .types import AssistantConfig

LOGGER = get_structured_logger("ai.config")


def _get_from_settings(settings: Any, path: str) -> Any:
    """
    Recupera un valore da Settings o da un Mapping usando una path dot-separated.
    Tollerante ad assenze: restituisce None se non risolvibile.
    """
    parts = path.split(".")

    if hasattr(settings, "get"):
        try:
            return settings.get(path)
        except Exception:
            pass

    if isinstance(settings, Mapping):
        current: Any = settings
        for part in parts:
            if isinstance(current, Mapping) and part in current:
                current = current.get(part)
            else:
                return None
        return current

    return None


def _extract_context_settings(ctx: Any) -> Tuple[Optional[Settings], Mapping[str, Any]]:
    raw = getattr(ctx, "settings", None)
    if isinstance(raw, Settings):
        try:
            return raw, raw.as_dict()
        except Exception:
            return raw, {}
    if isinstance(raw, Mapping):
        return None, raw
    as_dict = getattr(raw, "as_dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            if isinstance(data, Mapping):
                return None, data
        except Exception:
            pass
    return None, {}


def _optional_env(name: str) -> Optional[str]:
    try:
        value = get_env_var(name)
    except KeyError:
        return None
    except Exception:
        return None
    return value.strip() if isinstance(value, str) else None


def _resolve_assistant_env(
    settings_obj: Optional[Settings], settings_payload: Mapping[str, Any], default_env: str
) -> str:
    if isinstance(settings_obj, Settings):
        candidate = getattr(settings_obj, "vision_assistant_env", None)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        candidate = vision_cfg.get("assistant_id_env")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return default_env


def _resolve_model_from_settings(settings_obj: Optional[Settings], settings_payload: Mapping[str, Any]) -> str:
    if isinstance(settings_obj, Settings):
        try:
            candidate = settings_obj.vision_model
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        except Exception:
            pass
    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        candidate = vision_cfg.get("model")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    candidate = settings_payload.get("vision_model")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def _resolve_model_from_assistant(client: Any, assistant_id: str) -> str:
    assistants = getattr(client, "assistants", None)
    if assistants is None:
        beta = getattr(client, "beta", None)
        assistants = getattr(beta, "assistants", None)
    if not assistants:
        return ""
    try:
        assistant = assistants.retrieve(assistant_id)
    except Exception as exc:  # pragma: no cover - best-effort
        LOGGER.warning("ai.config.assistant_model.error", extra={"assistant_id": assistant_id, "error": str(exc)})
        return ""
    model = getattr(assistant, "model", None)
    return model.strip() if isinstance(model, str) else ""


def _resolve_vision_use_kb(
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
) -> bool:
    env_value = _optional_env("VISION_USE_KB")
    if env_value is not None:
        normalized = env_value.strip().lower()
        return normalized not in {"0", "false", "no", "off"}

    if isinstance(settings_obj, Settings):
        try:
            return bool(settings_obj.vision_settings.use_kb)
        except Exception:
            pass

    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        raw = vision_cfg.get("use_kb")
        if isinstance(raw, bool):
            return raw

    return True


def _resolve_vision_strict_output(
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
    base_dir: Optional[Any],
) -> bool:
    if isinstance(settings_obj, Settings):
        try:
            return bool(settings_obj.vision_settings.strict_output)
        except Exception:
            pass

    vision_cfg = settings_payload.get("vision")
    if isinstance(vision_cfg, Mapping):
        raw = vision_cfg.get("strict_output")
        if isinstance(raw, bool):
            return raw

    if base_dir:
        try:
            fallback_settings = Settings.load(base_dir)
            return bool(fallback_settings.vision_settings.strict_output)
        except Exception:
            pass

    return True


def resolve_vision_config(ctx: Any, *, override_model: Optional[str] = None) -> AssistantConfig:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    base_dir = getattr(ctx, "base_dir", None)

    assistant_env = _resolve_assistant_env(settings_obj, settings_payload, default_env="OBNEXT_ASSISTANT_ID")
    assistant_id = _optional_env(assistant_env) or _optional_env("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {assistant_env} (o ASSISTANT_ID) nell'ambiente.")

    resolved_model = (override_model or "").strip()
    if not resolved_model:
        resolved_model = _resolve_model_from_settings(settings_obj, settings_payload)
    if not resolved_model:
        client = make_openai_client()
        resolved_model = _resolve_model_from_assistant(client, assistant_id)
    if not resolved_model:
        raise ConfigError(
            "Modello Vision non configurato: imposta vision.model nel config o assegna un modello all'assistant "
            f"{assistant_id}."
        )

    use_kb = _resolve_vision_use_kb(settings_obj, settings_payload)
    strict_output = _resolve_vision_strict_output(settings_obj, settings_payload, base_dir)

    return AssistantConfig(
        model=resolved_model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=use_kb,
        strict_output=strict_output,
    )


def _resolve_assistant_env_generic(settings: Any, path: str, default_env: str) -> str:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return default_env


def _resolve_assistant_id(env_name: str) -> str:
    try:
        return get_env_var(env_name, required=True)
    except KeyError as exc:
        raise ConfigError(f"Assistant ID mancante: imposta la variabile {env_name}.") from exc


def _resolve_model(settings: Any, path: str, *, default: Optional[str] = None) -> str:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if default and default.strip():
        return default.strip()
    raise ConfigError(f"Modello non configurato per {path}.")


def _resolve_bool(settings: Any, path: str, default: Optional[bool]) -> Optional[bool]:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, bool):
        return candidate
    return default


def _build_assistant_config(
    *,
    settings: Any,
    model_path: str,
    assistant_env_path: str,
    default_env: str,
    use_kb_path: Optional[str] = None,
    strict_output_path: Optional[str] = None,
    default_use_kb: Optional[bool] = None,
    default_strict_output: Optional[bool] = None,
    model_default: Optional[str] = None,
) -> AssistantConfig:
    assistant_env = _resolve_assistant_env_generic(settings, assistant_env_path, default_env)
    model = _resolve_model(settings, model_path, default=model_default)
    assistant_id = _resolve_assistant_id(assistant_env)
    use_kb = _resolve_bool(settings, use_kb_path, default_use_kb) if use_kb_path else None
    strict_output = _resolve_bool(settings, strict_output_path, default_strict_output) if strict_output_path else None
    return AssistantConfig(
        model=model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=use_kb,
        strict_output=strict_output,
    )


def resolve_kgraph_config(settings: Any, assistant_env_override: Optional[str] = None) -> AssistantConfig:
    assistant_env = assistant_env_override or _resolve_assistant_env_generic(
        settings, "ai.kgraph.assistant_id_env", "KGRAPH_ASSISTANT_ID"
    )
    assistant_id = _optional_env(assistant_env)
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {assistant_env} (o ASSISTANT_ID) nell'ambiente.")

    raw_model = _get_from_settings(settings, "ai.kgraph.model")
    model = raw_model.strip() if isinstance(raw_model, str) else ""
    if not model:
        client = make_openai_client()
        model = _resolve_model_from_assistant(client, assistant_id)
    if not model:
        raise ConfigError(
            "Modello KGraph non configurato: imposta ai.kgraph.model o assegna un modello all'assistant "
            f"{assistant_id}."
        )

    return AssistantConfig(model=model, assistant_id=assistant_id, assistant_env=assistant_env)


def resolve_prototimmy_config(settings: Any) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.prototimmy.model",
        assistant_env_path="ai.prototimmy.assistant_id_env",
        default_env="PROTOTIMMY_ID",
        use_kb_path="ai.prototimmy.use_kb",
        default_use_kb=True,
    )


def resolve_planner_config(settings: Any) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.planner_assistant.model",
        assistant_env_path="ai.planner_assistant.assistant_id_env",
        default_env="PLANNER_ASSISTANT_ID",
        use_kb_path="ai.planner_assistant.use_kb",
        default_use_kb=True,
    )


def resolve_ocp_executor_config(settings: Any) -> AssistantConfig:
    return _build_assistant_config(
        settings=settings,
        model_path="ai.ocp_executor.model",
        assistant_env_path="ai.ocp_executor.assistant_id_env",
        default_env="OCP_EXECUTOR_ASSISTANT_ID",
        use_kb_path="ai.ocp_executor.use_kb",
        default_use_kb=True,
    )
