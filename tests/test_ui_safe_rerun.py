from __future__ import annotations

import sys
import types

import pytest

import src.ui.app as app
import src.ui.landing_slug as landing


def test_safe_streamlit_rerun_noop_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(app, "st", None, raising=True)
    app._safe_streamlit_rerun()


def test_safe_streamlit_rerun_calls_rerun(monkeypatch) -> None:
    called: dict[str, bool] = {}

    class Stub:
        def rerun(self) -> None:
            called["run"] = True

    monkeypatch.setattr(app, "st", Stub(), raising=True)
    app._safe_streamlit_rerun()
    assert called.get("run") is True


def test_safe_streamlit_rerun_propagates_rerun_exception(monkeypatch) -> None:
    class Stub:
        def rerun(self) -> None:
            raise app.RerunException(None)

    monkeypatch.setattr(app, "st", Stub(), raising=True)
    with pytest.raises(app.RerunException):
        app._safe_streamlit_rerun()


def test_safe_rerun_delegates_to_app_helper(monkeypatch) -> None:
    calls: dict[str, bool] = {}

    def _fake_rerun() -> None:
        calls["called"] = True

    dummy_app = types.SimpleNamespace(_safe_streamlit_rerun=_fake_rerun)
    monkeypatch.setitem(sys.modules, "src.ui.app", dummy_app)
    monkeypatch.setattr(landing, "st", types.SimpleNamespace(), raising=False)

    landing._safe_rerun()

    assert calls.get("called") is True
