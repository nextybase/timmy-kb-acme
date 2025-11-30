# SPDX-License-Identifier: GPL-3.0-only
import logging

import pytest

import timmy_kb_coder as coder


def test_load_client_cfg_logs_warning_on_failure(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    def _boom(*_: object, **__: object):
        raise RuntimeError("no config")

    monkeypatch.setattr(coder.ClientContext, "load", staticmethod(_boom))

    caplog.set_level(logging.WARNING)

    cfg = coder._load_client_cfg("slug")  # noqa: SLF001

    assert cfg == {}
    assert any("coder.config.unavailable" in record.message for record in caplog.records), caplog.text
