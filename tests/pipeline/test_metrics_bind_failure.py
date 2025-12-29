# SPDX-License-Identifier: GPL-3.0-only
import logging

import pytest

from pipeline import metrics


def test_start_metrics_server_once_raises_and_logs_on_bind_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="pipeline.metrics")
    monkeypatch.setattr(metrics, "_PROM_AVAILABLE", True)
    monkeypatch.setattr(metrics, "_METRICS_STARTED", False)
    monkeypatch.setattr(metrics, "start_http_server", lambda port: (_ for _ in ()).throw(RuntimeError("bind failed")))

    with pytest.raises(RuntimeError):
        metrics.start_metrics_server_once(1234)

    assert metrics._METRICS_STARTED is False
    rec = next((r for r in caplog.records if r.getMessage() == "observability.metrics.bind_failed"), None)
    assert rec is not None
    assert getattr(rec, "port", None) == 1234
