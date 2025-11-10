# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Any, List

import pytest

from ui.pages import logs_panel as page


class _StreamlitStub:
    def __init__(self) -> None:
        self.subheaders: List[str] = []
        self.info_messages: List[str] = []
        self.write_calls: List[str] = []

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def info(self, message: Any) -> None:
        self.info_messages.append(str(message))

    def write(self, message: Any) -> None:
        msg = str(message)
        self.write_calls.append(msg)
        self.info_messages.append(msg)


@pytest.fixture()
def streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> _StreamlitStub:
    stub = _StreamlitStub()

    def _fake_header(_slug: Any) -> None:
        return None

    def _fake_sidebar(_slug: Any) -> None:
        return None

    monkeypatch.setattr(page, "st", stub)
    monkeypatch.setattr(page, "header", _fake_header)
    monkeypatch.setattr(page, "sidebar", _fake_sidebar)
    return stub


def test_placeholder_page_shows_message(streamlit_stub: _StreamlitStub) -> None:
    page.main()

    assert streamlit_stub.subheaders == ["Log dashboard"]
    assert any("in costruzione" in msg for msg in streamlit_stub.info_messages)
    assert any("Slug attivo" in msg for msg in streamlit_stub.write_calls)
