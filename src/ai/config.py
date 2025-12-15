# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple, TypedDict, cast

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings

from .client_factory import make_openai_client
from .types import AssistantConfig

LOGGER = get_structured_logger("ai.config")


class VisionCfg(TypedDict, total=False):
    assistant_id_env: str
    model: str
    use_kb: bool
    strict_output: bool


class AssistantSectionCfg(TypedDict, total=False):
    model: str
    assistant_id_env: str
    use_kb: bool
    strict_output: bool


class AiCfgRoot(TypedDict, total=False):
    vision: VisionCfg
    ai: Mapping[str, AssistantSectionCfg]


def _vision_section(payload: Mapping[str, Any]) -> Optional[VisionCfg]:
    candidate = payload.get("vision")
    if isinstance(candidate, Mapping):
        return cast(VisionCfg, candidate)
    return None


def _ai_section(payload: Mapping[str, Any], name: str) -> Optional[AssistantSectionCfg]:
    ai_payload = payload.get("ai")
    if isinstance(ai_payload, Mapping):
        candidate = ai_payload.get(name)
        if isinstance(candidate, Mapping):
            return cast(AssistantSectionCfg, candidate)
    return None


def _as_mapping(source: Any) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    as_dict = getattr(source, "as_dict", None)
    if callable(as_dict):
        try:
            data = as_dict()
            if isinstance(data, Mapping):
                return data
        except Exception:
            pass
    return {}


def _get_from_settings(settings: Any, path: str, default: Any = None) -> Any:
    """
    Recupera un valore da Settings o da un Mapping usando una path dot-separated.
    - Prima prova settings.get(path); se restituisce un valore non-None, lo ritorna.
    - Altrimenti prova a navigare settings.as_dict() (se esiste) o il mapping stesso.
    - Se una chiave manca, restituisce default.
    """
    parts = path.split(".")

    # 1) Tentativo diretto via .get (se presente)
    if hasattr(settings, "get"):
        try:
            value = settings.get(path)
            if value is not None:
                return value
        except Exception:
            pass

    # 2) Fallback: as_dict() oppure mapping diretto
    mapping: Any = None
    if hasattr(settings, "as_dict"):
        try:
            mapping = settings.as_dict()
        except Exception:
            mapping = None
    if mapping is None and isinstance(settings, Mapping):
        mapping = settings
    if not isinstance(mapping, Mapping):
        return default

    current: Any = mapping
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current.get(part)
        else:
            return default
    return current


def _extract_context_settings(ctx: Any) -> Tuple[Optional[Settings], AiCfgRoot]:
    raw = getattr(ctx, "settings", None)
    mapping = _as_mapping(raw)
    if isinstance(raw, Settings):
        return raw, cast(AiCfgRoot, mapping)
    if mapping:
        return None, cast(AiCfgRoot, mapping)
    return None, cast(AiCfgRoot, {})


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
    vision_cfg = _vision_section(settings_payload)
    if vision_cfg:
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
    vision_cfg = _vision_section(settings_payload)
    if vision_cfg:
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

    vision_cfg = _vision_section(settings_payload)
    if vision_cfg:
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

    vision_cfg = _vision_section(settings_payload)
    if vision_cfg:
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


def _resolve_env_name_for_vision(settings_obj: Optional[Settings], settings_payload: Mapping[str, Any]) -> str:
    return _resolve_assistant_env(settings_obj, settings_payload, default_env="OBNEXT_ASSISTANT_ID")


def _resolve_model_for_vision(
    override_model: Optional[str],
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
    assistant_id: str,
) -> str:
    resolved_model = (override_model or "").strip()
    if resolved_model:
        return resolved_model
    resolved_model = _resolve_model_from_settings(settings_obj, settings_payload)
    if resolved_model:
        return resolved_model
    client = make_openai_client()
    resolved_model = _resolve_model_from_assistant(client, assistant_id)
    if resolved_model:
        return resolved_model
    raise ConfigError(
        "Modello Vision non configurato: imposta vision.model nel config o assegna un modello all'assistant "
        f"{assistant_id}."
    )


def resolve_vision_config(ctx: Any, *, override_model: Optional[str] = None) -> AssistantConfig:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    base_dir = getattr(ctx, "base_dir", None)

    assistant_env = _resolve_env_name_for_vision(settings_obj, settings_payload)
    assistant_id = _optional_env(assistant_env) or _optional_env("ASSISTANT_ID")
    if not assistant_id:
        raise ConfigError(f"Assistant ID non configurato: imposta {assistant_env} (o ASSISTANT_ID) nell'ambiente.")

    resolved_model = _resolve_model_for_vision(override_model, settings_obj, settings_payload, assistant_id)
    use_kb = _resolve_vision_use_kb(settings_obj, settings_payload)
    strict_output = _resolve_vision_strict_output(settings_obj, settings_payload, base_dir)

    return AssistantConfig(
        model=resolved_model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=use_kb,
        strict_output=strict_output,
    )


def _ai_section_name_from_path(path: str) -> Optional[str]:
    parts = path.split(".")
    if len(parts) >= 2 and parts[0] == "ai":
        return parts[1]
    return None


def _resolve_assistant_env_generic(settings: Any, path: str, default_env: str) -> str:
    candidate = _get_from_settings(settings, path)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    section_name = _ai_section_name_from_path(path)
    if section_name:
        section_cfg = _ai_section(_as_mapping(settings), section_name)
        if section_cfg:
            candidate = section_cfg.get("assistant_id_env")
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


def resolve_audit_assistant_config(settings: Any) -> AssistantConfig:
    """Agente `ai.audit_assistant`: non decide il 'cosa', non usa KB, nessun fallback.

    - Tipo: agente deterministico con contesto limitato e zero persistenza.
    - Autorizzato fallback model-from-assistant? NO.
    - Usa KB? NO.
    - Non introduce stato persistente né determina il contenuto.
    """
    assistant_env = _resolve_assistant_env_generic(
        settings, "ai.audit_assistant.assistant_id_env", "AUDIT_ASSISTANT_ID"
    )
    assistant_id = _resolve_assistant_id(assistant_env)
    model = _resolve_model(settings, "ai.audit_assistant.model")
    return AssistantConfig(
        model=model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=False,
        strict_output=None,
    )
