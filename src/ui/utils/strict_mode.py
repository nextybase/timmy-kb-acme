# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import os
from collections.abc import Mapping

_STRICT_TRUTHY = {"1", "true", "yes", "on"}


def is_ui_strict(env: Mapping[str, str] | None = None) -> bool:
    """UI strict mode: separato dal runtime CLI."""
    source = env if env is not None else os.environ
    value = source.get("TIMMY_UI_STRICT", "")
    return value.strip().lower() in _STRICT_TRUTHY
