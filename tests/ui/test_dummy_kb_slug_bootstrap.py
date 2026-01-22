# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import sys

import pytest

from tests.ui.stub_helpers import install_streamlit_stub


def test_dummy_kb_sets_slug_before_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = install_streamlit_stub(monkeypatch)
    monkeypatch.setattr("ui.utils.stubs.get_streamlit", lambda: st_stub, raising=True)
    sys.modules.pop("ui.pages.dummy_kb", None)
    page = importlib.import_module("ui.pages.dummy_kb")

    timeline: list[tuple[str, str | bool]] = []

    def _set_slug(slug: str, *, persist: bool, update_query: bool) -> None:
        timeline.append(("set", slug, persist, update_query))

    def _render_chrome(**_kwargs: object) -> None:
        timeline.append(("render",))

    monkeypatch.setattr(page, "set_active_slug", _set_slug, raising=True)
    monkeypatch.setattr(page, "render_chrome_then_require", _render_chrome, raising=True)
    monkeypatch.setattr(page, "get_slug", lambda: "dummy", raising=True)

    page.main()

    assert timeline[0] == ("set", "dummy", False, True)
    assert ("render",) in timeline
    render_index = timeline.index(("render",))
    assert ("set", "dummy", True, False) in timeline[render_index + 1 :]
