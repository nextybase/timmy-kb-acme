# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from importlib import import_module
from typing import Optional, Tuple


def otel_availability_details() -> Tuple[bool, Optional[str]]:
    try:
        import_module("opentelemetry.sdk.trace")
        return True, None
    except ImportError as exc:
        return False, str(exc)


def is_otel_available() -> bool:
    return otel_availability_details()[0]
