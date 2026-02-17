# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any

import pytest

from semantic import vocab_loader as vl


def test_safe_structured_warning_service_only_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    records: list[dict[str, Any]] = []

    class _FailingStructuredLogger:
        def warning(self, *_args, **_kwargs) -> None:
            raise TypeError("boom")

    class _FallbackRecorder:
        def warning(self, event: str, *, extra: dict[str, Any] | None = None, exc_info: bool = False) -> None:
            records.append(
                {
                    "event": event,
                    "extra": dict(extra or {}),
                    "exc_info": bool(exc_info),
                }
            )

    monkeypatch.setattr(vl, "LOGGER", _FailingStructuredLogger())
    monkeypatch.setattr(vl, "_FALLBACK_LOG", _FallbackRecorder())

    vl._safe_structured_warning("semantic.vocab.case_conflict", extra={"k": "v"})

    assert len(records) == 2
    assert records[0]["event"] == "structured_logger_failed"
    assert records[0]["extra"]["service_only"] is True
    assert records[0]["extra"]["service"] == "semantic.vocab_loader.observability"
    assert records[0]["exc_info"] is True
    assert records[1]["event"] == "semantic.vocab.case_conflict"
    assert records[1]["extra"]["service_only"] is True
    assert records[1]["extra"]["service"] == "semantic.vocab_loader.observability"
