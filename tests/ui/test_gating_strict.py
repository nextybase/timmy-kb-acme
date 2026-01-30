# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import sys

import pytest

from tests.ui.streamlit_stub import StreamlitStub
from tests.ui.test_manage_probe_normalized import register_streamlit_runtime


def test_visible_page_specs_blocks_on_gating_error_in_strict(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    stub = StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)
    monkeypatch.setenv("TIMMY_UI_STRICT", "1")

    import ui.gating as gating

    monkeypatch.setattr(gating, "get_active_slug", lambda: "dummy")

    def _boom(*_a, **_k):
        raise RuntimeError("normalized failed")

    monkeypatch.setattr(gating, "normalized_ready", _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            gating.visible_page_specs(gating.GateState(drive=True, vision=True, tags=True))

    assert any("ui.gating.normalized_ready_failed" in record.getMessage() for record in caplog.records)
