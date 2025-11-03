# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import DUMMY_SLUG
from tests.ui.stub_helpers import install_streamlit_stub


@pytest.mark.usefixtures("_stable_env")
def test_preview_stub_mode_start_and_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica che il ramo stub della preview appenda i log usando letture sicure."""

    st_stub = install_streamlit_stub(monkeypatch)
    monkeypatch.setattr("ui.utils.stubs.get_streamlit", lambda: st_stub, raising=True)

    monkeypatch.setattr("ui.chrome.render_chrome_then_require", lambda **_k: DUMMY_SLUG, raising=True)

    def _fake_load(cls, *, slug: str, **_kwargs):  # type: ignore[override]  # pylint: disable=unused-argument
        return SimpleNamespace(slug=slug, base_dir=tmp_path, redact_logs=False)

    monkeypatch.setattr("pipeline.context.ClientContext.load", classmethod(_fake_load), raising=True)
    monkeypatch.setattr(
        "pipeline.logging_utils.get_structured_logger",
        lambda *_a, **_k: logging.getLogger("test.preview"),
        raising=True,
    )

    monkeypatch.setenv("PREVIEW_MODE", "stub")
    monkeypatch.setenv("PREVIEW_LOG_DIR", "preview_logs")

    sys.modules.pop("ui.pages.preview", None)
    preview = importlib.import_module("ui.pages.preview")

    preview.REPO_ROOT = tmp_path  # reindirizza le scritture dello stub

    ctx = SimpleNamespace(slug=DUMMY_SLUG)
    logger = logging.getLogger("test.preview")

    name = preview._start_preview(ctx, logger, status_widget=None)
    preview._stop_preview(logger, name, status_widget=None)

    log_file = tmp_path / "preview_logs" / f"{DUMMY_SLUG}.log"
    content = log_file.read_text(encoding="utf-8")
    assert "PREVIEW_STUB_START" in content
    assert "PREVIEW_STUB_STOP" in content
