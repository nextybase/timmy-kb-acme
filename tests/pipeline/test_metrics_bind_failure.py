# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import logging

import pytest

from pipeline import metrics
from pipeline.exceptions import ConfigError


class _DummyCounter:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def labels(self, **_kwargs):
        return self

    def inc(self, *_args, **_kwargs) -> None:
        return None


class _DummyHistogram(_DummyCounter):
    def observe(self, *_args, **_kwargs) -> None:
        return None


def _stub_require_prometheus(module, start_fn) -> None:
    module._PROMETHEUS_COUNTER = _DummyCounter
    module._PROMETHEUS_HISTOGRAM = _DummyHistogram
    module.start_http_server = start_fn


def test_start_metrics_server_once_raises_and_logs_on_bind_failure(monkeypatch, caplog):
    monkeypatch.setenv("TIMMY_METRICS_ENABLED", "1")
    module = importlib.reload(metrics)
    caplog.set_level(logging.ERROR, logger="pipeline.metrics")
    module._METRICS_STARTED = False
    module._METRICS_INITIALIZED = False
    monkeypatch.setattr(
        module,
        "_require_prometheus",
        lambda: _stub_require_prometheus(module, lambda port: (_ for _ in ()).throw(RuntimeError("bind failed"))),
    )

    with pytest.raises(RuntimeError):
        module.start_metrics_server_once(1234)

    assert module._METRICS_STARTED is False
    rec = next((r for r in caplog.records if r.getMessage() == "observability.metrics.bind_failed"), None)
    assert rec is not None
    assert getattr(rec, "port", None) == 1234


def test_start_metrics_server_requires_prometheus(monkeypatch):
    monkeypatch.setenv("TIMMY_METRICS_ENABLED", "1")
    module = importlib.reload(metrics)
    module._METRICS_STARTED = False
    module._METRICS_INITIALIZED = False
    monkeypatch.setattr(
        module,
        "_require_prometheus",
        lambda: (_ for _ in ()).throw(ConfigError("missing", file_path="prometheus_client")),
    )

    with pytest.raises(ConfigError):
        module.start_metrics_server_once()


def test_start_metrics_server_skips_when_not_requested(monkeypatch, caplog):
    monkeypatch.delenv("TIMMY_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("TIMMY_METRICS_PORT", raising=False)
    module = importlib.reload(metrics)
    module._METRICS_STARTED = False
    module._METRICS_INITIALIZED = False
    caplog.set_level(logging.INFO, logger="pipeline.metrics")

    module.start_metrics_server_once()

    assert module._METRICS_STARTED is False
    rec = next((r for r in caplog.records if r.getMessage() == "observability.metrics.skipped"), None)
    assert rec is not None


def test_metrics_record_failure_is_reported_once(monkeypatch):
    module = importlib.reload(metrics)

    class _FailingCounter:
        def labels(self, **_kwargs):
            return self

        def inc(self, *_args, **_kwargs) -> None:
            raise RuntimeError("metrics write failed")

    calls: list[tuple[str, object]] = []

    def _fake_error(msg, **kwargs):
        calls.append((msg, kwargs.get("extra")))

    module._METRICS_RECORD_FAILURE_REPORTED = False
    module._METRICS_INITIALIZED = True
    module.documents_processed_total = _FailingCounter()
    monkeypatch.setattr(module._log, "error", _fake_error)

    module.record_document_processed("acme", 1)
    module.record_document_processed("acme", 1)

    assert len(calls) == 1
    assert calls[0][0] == "observability.metrics.record_failed"
