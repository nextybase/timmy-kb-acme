# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
import sys

import pytest

from tests.ui.stub_helpers import install_streamlit_stub


def test_sidebar_slug_less_does_not_call_clients_store(monkeypatch: pytest.MonkeyPatch) -> None:
    install_streamlit_stub(monkeypatch)
    sys.modules.pop("ui.chrome", None)
    chrome = importlib.import_module("ui.chrome")

    monkeypatch.setattr(chrome, "render_sidebar_brand", lambda **_k: None, raising=True)

    def _boom():
        raise AssertionError("clients_store called without slug")

    monkeypatch.setattr(chrome, "get_clients", _boom, raising=True)

    chrome.sidebar(None)
