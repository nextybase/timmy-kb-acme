# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
from collections.abc import Mapping

_STRICT_TRUTHY = {"1", "true", "yes", "on"}


def is_beta_strict(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    value = source.get("TIMMY_BETA_STRICT", "")
    return value.strip().lower() in _STRICT_TRUTHY
