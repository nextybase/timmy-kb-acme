# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from timmy_kb.cli import raw_ingest


def _stub_context() -> ClientContext:
    return ClientContext(slug="lock-proof")


def test_read_transformer_lock_missing_section(monkeypatch):
    monkeypatch.setattr(raw_ingest, "get_client_config", lambda *_: {})
    with pytest.raises(ConfigError) as excinfo:
        raw_ingest._read_transformer_lock(_stub_context())
    assert "transformer_lock" in str(excinfo.value)


def test_validate_transformer_lock_mismatch():
    expected = {
        "name": "pdf_text_v1",
        "version": "1.0.0",
        "ruleset_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }

    class DummyTransform:
        transformer_name = "pdf_text_v1"
        transformer_version = "1.0.0"
        ruleset_hash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    with pytest.raises(ConfigError) as excinfo:
        raw_ingest._ensure_transformer_lock_matches(expected, DummyTransform(), context=_stub_context())
    assert "mismatch" in str(excinfo.value).lower()
