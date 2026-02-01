# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import types

import pipeline.capabilities.otel as otel_module
from pipeline.capabilities import is_otel_available


def test_is_otel_available_returns_false_when_import_missing(monkeypatch):
    def fake_details():
        return {"available": False, "reason": "backend missing"}

    monkeypatch.setattr(otel_module, "otel_availability_details", fake_details)

    assert not is_otel_available()
    availability = otel_module.otel_availability_details()
    assert not availability["available"]
    assert "missing" in availability["reason"]


def test_is_otel_available_true_when_module_present(monkeypatch):
    fake_module = types.ModuleType("opentelemetry.sdk.trace")

    def fake_import_module(name: str):
        return fake_module

    monkeypatch.setattr("pipeline.capabilities.otel.import_module", fake_import_module)

    assert is_otel_available()
    availability = otel_module.otel_availability_details()
    assert availability["available"]
    assert availability["reason"] is None
