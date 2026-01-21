# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any

from pipeline.exceptions import ConfigError

__all__ = [
    "validate_areas_list",
    "validate_area_dict",
    "validate_area_key",
]


def validate_areas_list(
    areas: object,
    *,
    error_message: str,
    min_len: int | None = None,
    max_len: int | None = None,
) -> list[Any]:
    if not isinstance(areas, list):
        raise ConfigError(error_message)
    count = len(areas)
    if count == 0:
        raise ConfigError(error_message)
    if min_len is not None and count < min_len:
        raise ConfigError(error_message)
    if max_len is not None and count > max_len:
        raise ConfigError(error_message)
    return areas


def validate_area_dict(area: object, *, error_message: str) -> dict[str, Any]:
    if not isinstance(area, dict):
        raise ConfigError(error_message)
    return area


def validate_area_key(area: dict[str, Any], *, key_field: str, error_message: str) -> str:
    raw_value = area.get(key_field)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ConfigError(error_message)
    return raw_value
