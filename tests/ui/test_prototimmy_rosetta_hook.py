# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging

from pipeline.exceptions import ConfigError
from ui.pages import prototimmy_chat


def test_prototimmy_rosetta_hook_logs_disabled_state(caplog):
    caplog.set_level(logging.INFO, logger="prototimmy.rosetta_hook")
    settings = prototimmy_chat._load_settings()
    prototimmy_chat._maybe_consult_rosetta(settings, user_input="test-input")
    record = [
        rec
        for rec in caplog.records
        if rec.name == "prototimmy.rosetta_hook" and rec.event == "prototimmy.rosetta_consult_attempt"
    ][-1]
    assert getattr(record, "enabled", None) is False
    assert getattr(record, "reason", None) == "rosetta.disabled"
    assert getattr(record, "slug", None) == (settings.client_name or "prototimmy")
    assert getattr(record, "message_snippet", None) is None


def test_prototimmy_rosetta_hook_logs_error_when_client_fails(caplog, monkeypatch):
    def broken_client(*, settings, slug=None, client_factory=None):
        raise ConfigError("missing creds")

    monkeypatch.setattr(prototimmy_chat, "get_rosetta_client", broken_client)
    settings = prototimmy_chat._load_settings()
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="prototimmy.rosetta_hook"):
        prototimmy_chat._maybe_consult_rosetta(settings, user_input="fail-case")
    records = [
        rec
        for rec in caplog.records
        if rec.name == "prototimmy.rosetta_hook" and rec.event == "prototimmy.rosetta_consult_error"
    ]
    assert records, "nessun log di errore Rosetta registrato"
    record = records[-1]
    assert getattr(record, "reason", None) == "rosetta.load_failure"
    assert getattr(record, "error_type", None) == "ConfigError"
    assert getattr(record, "enabled", None) is False
    assert "missing creds" in getattr(record, "error_message", "")


def test_prototimmy_rosetta_hook_runs_client_when_enabled(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="prototimmy.rosetta_hook")
    called = {"check": 0, "explain": 0}

    class DummyClient:
        def check_coherence(self, *, assertions, run_id=None, metadata=None):
            called["check"] += 1

        def explain(self, *, assertion_id=None, trace_id=None, run_id=None):
            called["explain"] += 1

    def stub_client(*, settings, slug=None, client_factory=None):
        return DummyClient()

    monkeypatch.setattr(prototimmy_chat, "get_rosetta_client", stub_client)
    settings = prototimmy_chat._load_settings()
    prototimmy_chat._maybe_consult_rosetta(settings, user_input="ok-case", run_id="run-1")
    assert called["check"] == 1
    assert called["explain"] == 1
    records = [
        rec
        for rec in caplog.records
        if rec.name == "prototimmy.rosetta_hook" and rec.event == "prototimmy.rosetta_consult_attempt"
    ]
    assert records, "nessuno log di tentativo Rosetta registrato"
    enabled_record = records[-1]
    assert getattr(enabled_record, "enabled", None) is True
    assert getattr(enabled_record, "reason", None) == "rosetta.enabled"
