# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from types import SimpleNamespace

from pipeline.exceptions import ConfigError
from timmy_kb.ui.onboarding_ui import build_navigation


class _DummyNavigation:
    def run(self) -> None:
        return None


class _DummyStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}

    def columns(self, *_args, **_kwargs):
        return []

    def navigation(self, _pages, *, position: str = "top"):
        return _DummyNavigation()


class _DummyStModule:
    @staticmethod
    def Page(path: str, *, title: str, url_path: str | None = None):
        return {"path": path, "title": title, "url_path": url_path}


def _visible_page_specs(_gates):
    return {"Onboarding": [SimpleNamespace(path="ui/pages/new_client.py", title="Nuovo cliente", url_path="new")]}


def test_build_navigation_skips_normalized_warning_on_configerror(caplog):
    st = _DummyStreamlit()
    logger = logging.getLogger("tests.ui.onboarding.configerror")

    def _raise_configerror(_slug: str) -> bool:
        raise ConfigError("workspace non inizializzato")

    caplog.set_level(logging.WARNING)
    build_navigation(
        st=st,
        logger=logger,
        compute_gates=lambda: {},
        visible_page_specs=_visible_page_specs,
        get_streamlit=lambda: _DummyStModule(),
        get_active_slug=lambda: "prova",
        has_normalized_markdown=_raise_configerror,
    )

    assert "ui.workspace.normalized_check_failed" not in [rec.getMessage() for rec in caplog.records]


def test_build_navigation_logs_normalized_warning_once_per_slug(caplog):
    st = _DummyStreamlit()
    logger = logging.getLogger("tests.ui.onboarding.runtimeerror")

    def _raise_runtime(_slug: str) -> bool:
        raise RuntimeError("boom")

    caplog.set_level(logging.WARNING)
    for _ in range(2):
        build_navigation(
            st=st,
            logger=logger,
            compute_gates=lambda: {},
            visible_page_specs=_visible_page_specs,
            get_streamlit=lambda: _DummyStModule(),
            get_active_slug=lambda: "prova",
            has_normalized_markdown=_raise_runtime,
        )

    messages = [rec.getMessage() for rec in caplog.records]
    assert messages.count("ui.workspace.normalized_check_failed") == 1
    assert st.session_state.get("_normalized_check_failed_logged::prova") is True
