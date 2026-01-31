# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from tests.conftest import DUMMY_SLUG
from tests.ui.stub_helpers import install_streamlit_stub


def _load_preview_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    st_stub = install_streamlit_stub(monkeypatch)
    monkeypatch.setattr("ui.utils.stubs.get_streamlit", lambda: st_stub, raising=True)
    monkeypatch.setattr("ui.chrome.render_chrome_then_require", lambda **_k: DUMMY_SLUG, raising=True)

    def _fake_load(cls, *, slug: str, **_kwargs):
        return SimpleNamespace(slug=slug, base_dir=tmp_path, redact_logs=False)

    monkeypatch.setattr("pipeline.context.ClientContext.load", classmethod(_fake_load), raising=True)
    monkeypatch.setattr(
        "pipeline.logging_utils.get_structured_logger",
        lambda *_a, **_k: logging.getLogger("test.preview"),
        raising=True,
    )
    monkeypatch.setenv("PREVIEW_MODE", "stub")

    sys.modules.pop("ui.pages.preview", None)
    preview = importlib.import_module("ui.pages.preview")
    preview.REPO_ROOT = tmp_path
    preview.DEFAULT_PREVIEW_LOG_DIR = preview.REPO_ROOT / "logs" / "preview"

    ctx = SimpleNamespace(slug=DUMMY_SLUG)
    logger = logging.getLogger("test.preview")
    return preview, ctx, logger, st_stub


def _configure_missing_log_dir_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PREVIEW_LOG_DIR", raising=False)


def _configure_missing_log_dir_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing_logs"
    monkeypatch.setenv("PREVIEW_LOG_DIR", str(missing_dir))


def _configure_invalid_log_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("file", encoding="utf-8")
    monkeypatch.setenv("PREVIEW_LOG_DIR", str(blocked))


@pytest.mark.usefixtures("_stable_env")
def test_preview_stub_mode_start_and_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica che il ramo stub della preview appenda i log usando letture sicure."""

    preview, ctx, logger, st_stub = _load_preview_page(monkeypatch, tmp_path)

    preview_dir = tmp_path / "preview_logs"
    preview_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PREVIEW_LOG_DIR", str(preview_dir))

    with pytest.raises(ConfigError):
        preview._start_preview(ctx, logger, status_widget=None)
    assert not st_stub.warning_messages


@pytest.mark.usefixtures("_stable_env")
def test_preview_stub_absolute_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    preview, ctx, logger, st_stub = _load_preview_page(monkeypatch, tmp_path)

    absolute_dir = tmp_path / "external_logs"
    absolute_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PREVIEW_LOG_DIR", str(absolute_dir))

    with pytest.raises(ConfigError):
        preview._start_preview(ctx, logger, status_widget=None)
    assert not st_stub.warning_messages


@pytest.mark.parametrize(
    "configurator",
    (
        _configure_missing_log_dir_env,
        _configure_missing_log_dir_path,
        _configure_invalid_log_dir,
    ),
    ids=("env_missing", "path_missing", "invalid_path"),
)
def test_preview_stub_log_dir_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configurator) -> None:
    preview, ctx, logger, _ = _load_preview_page(monkeypatch, tmp_path)
    configurator(monkeypatch, tmp_path)
    with pytest.raises(ConfigError):
        preview._start_preview(ctx, logger, status_widget=None)
