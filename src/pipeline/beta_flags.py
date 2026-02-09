# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from collections.abc import Mapping

_STRICT_TRUTHY = {"1", "true", "yes", "on"}
_NON_STRICT_VALUES = {"0", "false", "no", "off"}
_TEST_MODE_TRUTHY = {"1", "true", "yes", "on"}


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


def is_test_mode(env: Mapping[str, str] | None = None) -> bool:
    """Indica se TEST_MODE è attivo (solo valori truthy definiti)."""
    source = env if env is not None else os.environ
    raw_value = source.get("TEST_MODE")
    if raw_value is None:
        return False
    normalized = raw_value.strip().lower()
    if normalized == "":
        return False
    return normalized in _TEST_MODE_TRUTHY
