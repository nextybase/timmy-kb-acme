# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Optional

from pipeline.exceptions import ConfigError


def _normalize_string(value: Optional[str]) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def resolve_assistant_env(
    settings_value: Optional[str],
    payload_value: Optional[str],
    default_env_name: str,
) -> str:
    """
    Priorità per la variabile dell'assistant: settings -> payload -> default.

    :param settings_value: valore proveniente da Settings (es. vision_assistant_env).
    :param payload_value: valore dichiarato nel payload ai.<sezione>.assistant_id_env.
    :param default_env_name: nome di default (es. "OBNEXT_ASSISTANT_ID").
    :return: il nome della variabile ambiente effettivamente usata.
    """
    candidate = _normalize_string(settings_value)
    if candidate:
        return candidate
    candidate = _normalize_string(payload_value)
    if candidate:
        return candidate
    return default_env_name


def resolve_assistant_id(
    env_value: Optional[str],
    primary_env_name: str,
) -> str:
    """
    Restituisce l'assistant_id effettivo: preferisce la variabile primaria,
    poi il default. Solleva ConfigError se nessuna è impostata.
    """
    primary = _normalize_string(env_value)
    if primary:
        return primary
    raise ConfigError(
        f"Assistant ID mancante: imposta {primary_env_name} nell'ambiente.",
        code="assistant.id.missing",
        component="resolution",
    )


def resolve_model_precedence(
    override_model: Optional[str],
    settings_model: Optional[str],
    payload_model: Optional[str],
    assistant_model: Optional[str],
    *,
    error_message: str,
) -> str:
    """
    Precedenza modelli: override > settings > payload > assistant.
    Se nessun candidato è valido solleva ConfigError.
    """
    for candidate in (
        override_model,
        settings_model,
        payload_model,
        assistant_model,
    ):
        normalized = _normalize_string(candidate)
        if normalized:
            return normalized
    raise ConfigError(
        error_message,
        code="assistant.model.missing",
        component="resolution",
    )


def resolve_boolean_flag(
    env_override: Optional[bool],
    settings_value: Optional[bool],
    payload_value: Optional[bool],
    *,
    default: bool,
) -> bool:
    """
    Risolve flag booleani secondo la precedenza:
    - env_override (se provided)
    - settings_value
    - payload_value (if bool)
    - default
    """
    if env_override is not None:
        return env_override
    if settings_value is not None:
        return settings_value
    if payload_value is not None:
        return payload_value
    return default
