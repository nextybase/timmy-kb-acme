# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import builtins
import logging

import pytest

from pipeline import tracing


def test_tracing_disabled_logs_structured(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(tracing, "_TRACING_DISABLED_EMITTED", set(), raising=True)
    monkeypatch.setattr(tracing, "_TRACING_DISABLED_LOGGED", False, raising=True)

    def _no_print(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("print() non atteso")

    monkeypatch.setattr(builtins, "print", _no_print, raising=True)

    with caplog.at_level(logging.INFO):
        tracing.ensure_tracer(enable_tracing=False)
        tracing.ensure_tracer(enable_tracing=False)

    records = [record for record in caplog.records if record.getMessage() == "observability.tracing.disabled"]
    assert records
    assert len(records) == 1
    assert all(record.levelname == "INFO" for record in records)
    assert all(record.name == "pipeline.observability" for record in records)
