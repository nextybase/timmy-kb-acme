# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging

import pytest

from pipeline import context
from pipeline.exceptions import ConfigError


class _FailingLogger(logging.Logger):
    def setLevel(self, level: int) -> None:  # pragma: no cover
        raise RuntimeError("boom")


def test_apply_logger_level_strict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(context, "is_beta_strict", lambda: True, raising=False)
    logger = _FailingLogger("strict")
    with pytest.raises(ConfigError) as excinfo:
        context.ClientContext._apply_logger_level(logger, logging.INFO)
    assert excinfo.value.code == "logging.level.apply_failed"


def test_apply_logger_level_non_strict_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(context, "is_beta_strict", lambda: False, raising=False)
    logger = _FailingLogger("non-strict")
    caplog.set_level(logging.WARNING, logger=context.LOGGER.name)
    context.ClientContext._apply_logger_level(logger, logging.INFO)
    assert any(
        rec.message == "context.logger_level_apply_failed"
        and getattr(rec, "service_only", None) is True
        for rec in caplog.records
    )


def test_apply_logger_level_handler_failure_does_not_crash(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(context, "is_beta_strict", lambda: False, raising=False)
    logger = logging.Logger("handler-test")

    class _FailingHandler(logging.StreamHandler):
        def setLevel(self, level: int) -> None:  # pragma: no cover
            raise RuntimeError("boom handler")

    handler = _FailingHandler()
    logger.addHandler(handler)
    caplog.set_level(logging.WARNING, logger=context.LOGGER.name)

    context.ClientContext._apply_logger_level(logger, logging.INFO)

    assert any(
        rec.message == "context.logger_level_apply_failed"
        and getattr(rec, "service_only", None) is True
        for rec in caplog.records
    )
