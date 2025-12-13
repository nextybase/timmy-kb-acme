# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from importlib import import_module
from typing import cast

from pipeline.types import CapabilityAvailability


def otel_availability_details() -> CapabilityAvailability:
    try:
        import_module("opentelemetry.sdk.trace")
        return cast(CapabilityAvailability, (True, None))
    except ImportError as exc:
        return cast(CapabilityAvailability, (False, str(exc)))


def is_otel_available() -> bool:
    return otel_availability_details()[0]
