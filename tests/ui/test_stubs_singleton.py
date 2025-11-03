# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import builtins

import pytest

from ui.utils import stubs


@pytest.fixture(autouse=True)
def reset_stub() -> None:
    stubs.reset_streamlit_stub()


def _force_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "streamlit":
            raise ModuleNotFoundError("stubbed streamlit")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


def test_get_streamlit_returns_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_stub(monkeypatch)
    stub1 = stubs.get_streamlit()
    stub1.session_state["foo"] = "bar"
    stub2 = stubs.get_streamlit()
    assert stub1 is stub2
    assert stub2.session_state["foo"] == "bar"


def test_reset_streamlit_stub_clears_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_stub(monkeypatch)
    stub = stubs.get_streamlit()
    stub.session_state["foo"] = "bar"
    stub.query_params["slug"] = "dummy"
    stubs.reset_streamlit_stub()
    assert stub.session_state == {}
    assert stub.query_params == {}
