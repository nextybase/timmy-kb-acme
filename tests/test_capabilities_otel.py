# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import types

from pipeline.capabilities import is_otel_available
from pipeline.capabilities.otel import otel_availability_details


def test_is_otel_available_returns_false_when_import_missing(monkeypatch):
    def fake_import_module(name: str):
        raise ImportError("ebackend missing")

    monkeypatch.setattr("pipeline.capabilities.otel.import_module", fake_import_module)

    assert not is_otel_available()
    available, reason = otel_availability_details()
    assert not available
    assert "missing" in reason


def test_is_otel_available_true_when_module_present(monkeypatch):
    fake_module = types.ModuleType("opentelemetry.sdk.trace")

    def fake_import_module(name: str):
        return fake_module

    monkeypatch.setattr("pipeline.capabilities.otel.import_module", fake_import_module)

    assert is_otel_available()
    available, reason = otel_availability_details()
    assert available
    assert reason is None
