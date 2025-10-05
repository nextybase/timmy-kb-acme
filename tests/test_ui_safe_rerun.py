from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.ui.app as app


def test_safe_streamlit_rerun_noop_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(app, "st", None, raising=True)
    app._safe_streamlit_rerun()


def test_safe_streamlit_rerun_falls_back_to_experimental(monkeypatch) -> None:
    called = {}
    stub = SimpleNamespace(experimental_rerun=lambda: called.setdefault("run", True))
    monkeypatch.setattr(app, "st", stub, raising=True)
    app._safe_streamlit_rerun()
    assert called.get("run") is True


def test_safe_streamlit_rerun_propagates_rerun_exception(monkeypatch) -> None:
    class Stub:
        def rerun(self) -> None:
            raise app.RerunException(None)

    monkeypatch.setattr(app, "st", Stub(), raising=True)
    with pytest.raises(app.RerunException):
        app._safe_streamlit_rerun()
