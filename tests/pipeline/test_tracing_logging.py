# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline import tracing


def test_tracing_disabled_logs_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_TRACING_DISABLED_EMITTED", set(), raising=True)
    monkeypatch.setattr(tracing, "_OTEL_DISABLED_LOGGED", False, raising=True)
    monkeypatch.setattr(tracing, "_OTEL_IMPORT_OK", True, raising=True)

    calls: list[tuple[str, dict]] = []

    def _fake_info(msg: str, *args: object, **kwargs: object) -> None:
        extra = kwargs.get("extra") or {}
        if msg == "observability.tracing.disabled":
            calls.append((msg, dict(extra)))

    monkeypatch.setattr(tracing._log, "info", _fake_info, raising=True)

    tracing.ensure_tracer(enable_tracing=False)
    tracing.ensure_tracer(enable_tracing=False)

    assert calls, "atteso almeno un log observability.tracing.disabled"
    assert len(calls) == 1, "atteso un solo log per reason (disabled_by_flag)"
    assert calls[0][1].get("reason") == "disabled_by_flag"
