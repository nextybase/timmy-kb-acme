# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from typing import Any, Dict, List

import pytest


class _ColumnStub:
    def __enter__(self) -> "_ColumnStub":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False


class _StreamlitLandingStub:
    def __init__(self) -> None:
        self.session_state: Dict[str, Any] = {}
        self.button_calls: List[tuple[str, Dict[str, Any]]] = []

    def html(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def columns(self, spec) -> tuple[_ColumnStub, _ColumnStub, _ColumnStub]:
        return _ColumnStub(), _ColumnStub(), _ColumnStub()

    @contextmanager
    def form(self, *_args: Any, **_kwargs: Any):
        yield object()

    def form_submit_button(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def text_input(self, *_args: Any, **_kwargs: Any) -> str:
        return ""

    def button(self, label: str, **kwargs: Any) -> bool:
        self.button_calls.append((label, kwargs))
        return False

    def file_uploader(self, *_args: Any, **_kwargs: Any):
        return None


def _load_landing(monkeypatch: pytest.MonkeyPatch, st_stub: _StreamlitLandingStub) -> Any:
    monkeypatch.setitem(sys.modules, "streamlit", st_stub)

    import ui.utils.branding

    monkeypatch.setattr(ui.utils.branding, "render_brand_header", lambda **_k: None)

    sys.modules.pop("ui.landing_slug", None)
    return importlib.import_module("ui.landing_slug")


def test_exit_button_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitLandingStub()
    monkeypatch.delenv("UI_ALLOW_EXIT", raising=False)

    landing = _load_landing(monkeypatch, st_stub)

    landing.render_landing_slug(log=None)

    assert not any(label == "Esci" for label, _ in st_stub.button_calls)


def test_exit_button_shown_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    st_stub = _StreamlitLandingStub()
    monkeypatch.setenv("UI_ALLOW_EXIT", "1")

    landing = _load_landing(monkeypatch, st_stub)

    landing.render_landing_slug(log=None)

    assert any(label == "Esci" for label, _ in st_stub.button_calls)
    kwargs = next(kwargs for label, kwargs in st_stub.button_calls if label == "Esci")
    assert kwargs.get("width") == "stretch"
