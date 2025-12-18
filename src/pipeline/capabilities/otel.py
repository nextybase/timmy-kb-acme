# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from importlib import import_module
from typing import cast

from pipeline.types import CapabilityAvailability


def otel_availability_details() -> CapabilityAvailability:
    try:
        import_module("opentelemetry.sdk.trace")
        return {"available": True, "reason": None}
    except ImportError as exc:
        return {"available": False, "reason": str(exc)}


def is_otel_available() -> bool:
    availability = otel_availability_details()
    return cast(bool, availability["available"])
