# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import ai.responses as responses


def _dummy_client(output_text: str = "ok"):
    class DummyResponses:
        def create(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                output=[SimpleNamespace(type="output_text", text=SimpleNamespace(value=output_text))],
                status="completed",
                id="dummy-run",
                model="dummy-model",
            )

    return SimpleNamespace(responses=DummyResponses())


def _find_invocation_record(caplog: pytest.CaptureFixture[str]) -> logging.LogRecord:
    for record in caplog.records:
        if getattr(record, "event", "") == "ai.invocation":
            return record
    raise AssertionError("ai.invocation record not found")


def test_run_json_model_logs_invocation(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="ai.responses")
    monkeypatch.setattr(responses, "make_openai_client", lambda: _dummy_client('{"ok": true}'))
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    responses.run_json_model(
        model="vision-model",
        messages=[{"role": "user", "content": "{}"}],
        response_format={"type": "json_object"},
        invocation={
            "component": "vision",
            "operation": "vision.provision",
            "assistant_id": "asst-vision",
            "strict_output": True,
            "use_kb": True,
            "retention_days": 7,
            "request_tag": "vision-test",
        },
    )

    record = _find_invocation_record(caplog)
    assert record.component == "vision"
    assert record.retention_days == 7
    assert "not-a-real-key" not in record.getMessage()


def test_run_text_model_logs_invocation(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="ai.responses")
    monkeypatch.setattr(responses, "make_openai_client", lambda: _dummy_client("pong"))
    responses.run_text_model(
        model="proto-model",
        messages=[{"role": "user", "content": "ping"}],
        invocation={
            "component": "prototimmy",
            "operation": "prototimmy.chat",
            "step": "ping",
            "assistant_id": "asst-proto",
        },
    )

    record = _find_invocation_record(caplog)
    assert record.operation == "prototimmy.chat"
    assert record.step == "ping"
