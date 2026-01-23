# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Mapping, Optional, Tuple, TypedDict, cast

import pipeline.env_utils as env_utils
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings

from . import resolution
from .assistant_registry import _resolve_assistant_env_name
from .types import AssistantConfig

LOGGER = get_structured_logger("ai.vision_config")


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


def _vision_section(payload: Mapping[str, Any]) -> VisionCfg:
    # vision.* a root non supportato (hard cut)
    if "vision" in payload:
        LOGGER.error(
            "ai.vision_config.legacy_root_vision",
            extra={"path": "vision"},
        )
        raise ConfigError("Config legacy rilevata: sposta 'vision' sotto 'ai.vision' in config/config.yaml")

    # Schema attuale: ai.vision (config/config.yaml riorganizzato)
    ai_candidate = payload.get("ai")
    if isinstance(ai_candidate, Mapping):
        nested = ai_candidate.get("vision")
        if isinstance(nested, Mapping):
            return cast(VisionCfg, nested)
        if "vision" in ai_candidate:
            LOGGER.error(
                "ai.vision_config.section_invalid",
                extra={"path": "ai.vision", "error": "not_mapping"},
            )
            raise ConfigError("Sezione ai.vision non valida: atteso mapping", path="ai.vision")

    LOGGER.error(
        "ai.vision_config.section_missing",
        extra={"path": "ai.vision"},
    )
    raise ConfigError("Config Vision mancante: definire ai.vision in config/config.yaml", path="ai.vision")


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
        except Exception as exc:
            raise ConfigError(
                "Configurazione non convertibile: as_dict() fallita.",
                code="config.read.failed",
                component="vision_config",
            ) from exc
        if isinstance(data, Mapping):
            return data
        raise ConfigError(
            "Configurazione non convertibile: as_dict() non restituisce un mapping.",
            code="config.read.failed",
            component="vision_config",
        )
    raise ConfigError(
        "Configurazione non convertibile: atteso mapping.",
        code="config.read.failed",
        component="vision_config",
    )


def _extract_context_settings(ctx: Any) -> Tuple[Optional[Settings], AiCfgRoot]:
    raw = getattr(ctx, "settings", None)
    mapping = _as_mapping(raw)
    if isinstance(raw, Settings):
        return raw, cast(AiCfgRoot, mapping)
    if mapping:
        return None, cast(AiCfgRoot, mapping)
    return None, cast(AiCfgRoot, {})


def _optional_env(name: str) -> Optional[str]:
    raw_env_value = os.environ.get(name)
    if raw_env_value is not None and not str(raw_env_value).strip():
        raise ConfigError(
            f"Variabile ambiente vuota: {name}.",
            code="assistant.env.empty",
            component="vision_config",
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
            component="vision_config",
            env=name,
        ) from exc
    return value.strip() if isinstance(value, str) else None


def _resolve_assistant_env(
    settings_obj: Optional[Settings], settings_payload: Mapping[str, Any], default_env: str
) -> str:
    settings_value: Optional[str] = None
    if isinstance(settings_obj, Settings):
        candidate = getattr(settings_obj, "vision_assistant_env", None)
        if isinstance(candidate, str):
            settings_value = candidate
    payload_value: Optional[str] = None
    vision_cfg = _vision_section(settings_payload)
    candidate = vision_cfg.get("assistant_id_env")
    if isinstance(candidate, str):
        payload_value = candidate
    return resolution.resolve_assistant_env(settings_value, payload_value, default_env)


def _resolve_model_from_settings(settings_obj: Optional[Settings], settings_payload: Mapping[str, Any]) -> str:
    if isinstance(settings_obj, Settings):
        try:
            candidate = settings_obj.vision_model
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        except Exception:
            pass
    vision_cfg = _vision_section(settings_payload)
    candidate = vision_cfg.get("model")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    candidate = settings_payload.get("vision_model")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def _resolve_vision_use_kb(
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
) -> bool:
    env_flag: Optional[bool] = None
    env_value = _optional_env("VISION_USE_KB")
    if env_value is not None:
        normalized = env_value.strip().lower()
        env_flag = normalized not in {"0", "false", "no", "off"}

    settings_flag: Optional[bool] = None
    if isinstance(settings_obj, Settings):
        try:
            settings_flag = bool(settings_obj.vision_settings.use_kb)
        except Exception:
            settings_flag = None

    payload_flag: Optional[bool] = None
    vision_cfg = _vision_section(settings_payload)
    raw = vision_cfg.get("use_kb")
    if isinstance(raw, bool):
        payload_flag = raw

    return resolution.resolve_boolean_flag(env_flag, settings_flag, payload_flag, default=True)


@lru_cache(maxsize=16)
def _load_settings_cached(repo_root_dir: Optional[str]) -> Optional[Settings]:
    if not repo_root_dir:
        return None
    try:
        return Settings.load(repo_root_dir)
    except Exception as exc:
        LOGGER.warning(
            "ai.vision_config.settings_load_failed",
            extra={
                "repo_root_dir": repo_root_dir,
                "error": str(exc),
                "exc_type": type(exc).__name__,
            },
        )
        return None


def _resolve_vision_strict_output(
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
    repo_root_dir: Optional[Any],
) -> bool:
    settings_flag: Optional[bool] = None
    if isinstance(settings_obj, Settings):
        try:
            settings_flag = bool(settings_obj.vision_settings.strict_output)
        except Exception:
            settings_flag = None

    payload_flag: Optional[bool] = None
    vision_cfg = _vision_section(settings_payload)
    raw = vision_cfg.get("strict_output")
    if isinstance(raw, bool):
        payload_flag = raw

    fallback_flag: Optional[bool] = None
    if repo_root_dir:
        fallback_settings = _load_settings_cached(str(repo_root_dir))
        if fallback_settings is not None:
            fallback_flag = bool(fallback_settings.vision_settings.strict_output)

    default_value = fallback_flag if fallback_flag is not None else True
    return resolution.resolve_boolean_flag(None, settings_flag, payload_flag, default=default_value)


def _resolve_env_name_for_vision(settings_obj: Optional[Settings], settings_payload: Mapping[str, Any]) -> str:
    return _resolve_assistant_env(settings_obj, settings_payload, default_env="OBNEXT_ASSISTANT_ID")


_resolve_assistant_env_generic = _resolve_assistant_env_name


def _resolve_model_for_vision(
    override_model: Optional[str],
    settings_obj: Optional[Settings],
    settings_payload: Mapping[str, Any],
    assistant_id: str,
) -> str:
    override_candidate = (override_model or "").strip()
    if override_candidate:
        LOGGER.info(
            "ai.vision_config.model_resolved",
            extra={"source": "override", "model": override_candidate},
        )
        return override_candidate
    settings_candidate = _resolve_model_from_settings(settings_obj, settings_payload)
    if settings_candidate:
        LOGGER.info(
            "ai.vision_config.model_resolved",
            extra={"source": "settings", "model": settings_candidate},
        )
        return settings_candidate
    try:
        return resolution.resolve_model_precedence(
            override_candidate,
            settings_candidate,
            "",
            "",
            error_message=("Modello Vision non configurato: imposta vision.model nel config."),
        )
    except ConfigError as exc:
        raise ConfigError(
            str(exc),
            code="vision.model.missing",
            component="vision_config",
        ) from exc


def resolve_vision_config(ctx: Any, *, override_model: Optional[str] = None) -> AssistantConfig:
    """Micro-agente `vision`: non decide il 'cosa', produce risposte a contratto.

    - Tipo: Micro-agente stateless con input/output definiti.
    - default model-from-assistant: SI.
    - Usa KB: SÌ.
    """
    settings_obj, settings_payload = _extract_context_settings(ctx)
    repo_root_dir = getattr(ctx, "repo_root_dir", None)

    assistant_env = _resolve_env_name_for_vision(settings_obj, settings_payload)
    primary_env_value = _optional_env(assistant_env)
    assistant_id = resolution.resolve_assistant_id(
        primary_env_value,
        assistant_env,
    )

    resolved_model = _resolve_model_for_vision(override_model, settings_obj, settings_payload, assistant_id)
    use_kb = _resolve_vision_use_kb(settings_obj, settings_payload)
    strict_output = _resolve_vision_strict_output(settings_obj, settings_payload, repo_root_dir)

    return AssistantConfig(
        model=resolved_model,
        assistant_id=assistant_id,
        assistant_env=assistant_env,
        use_kb=use_kb,
        strict_output=strict_output,
    )


def resolve_vision_retention_days(ctx: Any) -> int:
    settings_obj, settings_payload = _extract_context_settings(ctx)
    slug = getattr(ctx, "slug", None)
    value: Optional[int] = None
    if isinstance(settings_obj, Settings):
        try:
            value = int(settings_obj.vision_snapshot_retention_days)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                "snapshot_retention_days non valido: atteso intero > 0.",
                code="vision.retention.invalid",
                component="vision_config",
                slug=slug,
            ) from exc
    else:
        vision_cfg = _vision_section(settings_payload)
        raw_value = vision_cfg.get("snapshot_retention_days")
        if raw_value is not None:
            try:
                value = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    "snapshot_retention_days non valido: atteso intero > 0.",
                    code="vision.retention.invalid",
                    component="vision_config",
                    slug=slug,
                ) from exc

    if value is None:
        raise ConfigError(
            "snapshot_retention_days mancante: definire ai.vision.snapshot_retention_days.",
            code="vision.retention.missing",
            component="vision_config",
            slug=slug,
        )
    if value <= 0:
        raise ConfigError(
            "snapshot_retention_days non valido: atteso intero > 0.",
            code="vision.retention.invalid",
            component="vision_config",
            slug=slug,
        )
    return value
