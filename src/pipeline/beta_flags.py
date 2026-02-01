# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
from collections.abc import Mapping

_STRICT_TRUTHY = {"1", "true", "yes", "on"}
_NON_STRICT_VALUES = {"0", "false", "no", "off"}


def is_beta_strict(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    raw_value = source.get("TIMMY_BETA_STRICT")
    if raw_value is None:
        return True

    normalized = raw_value.strip().lower()
    if normalized == "":
        return True

    if normalized in _STRICT_TRUTHY:
        return True

    if normalized in _NON_STRICT_VALUES:
        return False

    return True
