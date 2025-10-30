from __future__ import annotations

import importlib
import logging
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from tests.conftest import DUMMY_SLUG


class _ButtonColumn:
    def button(self, *_args: Any, **_kwargs: Any) -> bool:
        return False


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - no-op
        return None

    def columns(self, _spec: Any) -> tuple[_ButtonColumn, _ButtonColumn]:
        return (_ButtonColumn(), _ButtonColumn())

    def error(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - no-op
        return None

    def caption(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - no-op
        return None


@pytest.mark.usefixtures("_stable_env")
def test_preview_stub_mode_start_and_stop(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """In modalità stub l'import non deve fallire e la scrittura dei log deve essere path-safe."""

    # Streamlit stub per evitare interazioni reali
    stub = _StreamlitStub()
    monkeypatch.setattr("ui.utils.stubs.get_streamlit", lambda: stub, raising=True)

    # Evita dipendenze pesanti durante l'import
    monkeypatch.setattr("ui.chrome.render_chrome_then_require", lambda **_k: DUMMY_SLUG, raising=True)

    def _fake_load(cls, *, slug: str, **_kwargs: Any):  # type: ignore[override]
        return SimpleNamespace(slug=slug, base_dir=tmp_path, redact_logs=False)

    monkeypatch.setattr("pipeline.context.ClientContext.load", classmethod(_fake_load), raising=True)
    monkeypatch.setattr(
        "pipeline.logging_utils.get_structured_logger", lambda *a, **k: logging.getLogger("test.preview"), raising=True
    )

    # Imposta stub mode e directory log relativa
    monkeypatch.setenv("PREVIEW_MODE", "stub")
    monkeypatch.setenv("PREVIEW_LOG_DIR", "preview_logs")

    # Reimporta il modulo con le patch attive
    sys.modules.pop("ui.pages.preview", None)
    preview = importlib.import_module("ui.pages.preview")

    # Scrive i log nello sandbox temporaneo
    preview.REPO_ROOT = tmp_path

    ctx = SimpleNamespace(slug=DUMMY_SLUG)
    logger = logging.getLogger("test.preview")

    name = preview._start_preview(ctx, logger, status_widget=None)
    preview._stop_preview(logger, name, status_widget=None)

    log_file = tmp_path / "preview_logs" / f"{DUMMY_SLUG}.log"
    content = log_file.read_text(encoding="utf-8")
    assert "PREVIEW_STUB_START" in content
    assert "PREVIEW_STUB_STOP" in content
