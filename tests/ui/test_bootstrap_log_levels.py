# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pipeline.env_constants import REPO_ROOT_ENV
from pipeline.paths import get_repo_root
from tests.ui.streamlit_stub import StreamlitStub
from timmy_kb.ui import onboarding_ui
from ui import theme_enhancements
from ui.utils import branding


class _StreamlitModuleStub(StreamlitStub):
    __version__ = "1.50.0"

    def set_page_config(self, **_kwargs: object) -> None:
        return None


def test_ui_startup_logged_at_info(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    stub = _StreamlitModuleStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    monkeypatch.setattr(onboarding_ui, "_ensure_env_loaded_once", lambda: None, raising=True)
    monkeypatch.setattr(onboarding_ui, "_ensure_streamlit_api", lambda _st: None, raising=True)
    monkeypatch.setattr(
        onboarding_ui,
        "_hydrate_query_defaults",
        lambda: (_ for _ in ()).throw(RuntimeError("stop")),
        raising=True,
    )
    monkeypatch.setattr(onboarding_ui, "get_repo_root", lambda: Path("."), raising=True)
    monkeypatch.setattr(onboarding_ui, "build_identity", lambda: {}, raising=True)
    monkeypatch.setattr(onboarding_ui, "build_env_fingerprint", lambda: "fp", raising=True)
    monkeypatch.setattr(branding, "get_favicon_path", lambda _root: Path("favicon.ico"), raising=True)
    monkeypatch.setattr(onboarding_ui.config_store, "get_skip_preflight", lambda **_kwargs: False, raising=True)
    monkeypatch.setattr(theme_enhancements, "inject_theme_css", lambda: None, raising=True)

    logger = logging.getLogger("tests.ui_startup")
    logger.setLevel(logging.DEBUG)
    monkeypatch.setattr(onboarding_ui, "_lazy_bootstrap", lambda _root: logger, raising=True)

    with caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError):
            onboarding_ui.main()

    records = [record for record in caplog.records if record.getMessage() == "ui.startup"]
    assert records
    assert all(record.levelno == logging.INFO for record in records)


def test_repo_root_env_event_not_info(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo_root))

    with caplog.at_level(logging.INFO):
        _ = get_repo_root(allow_env=True)

    assert not any(record.getMessage() == "paths.repo_root.env" for record in caplog.records)
