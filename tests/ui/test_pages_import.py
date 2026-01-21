# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pipeline.exceptions import InvalidSlug
from tests.conftest import DUMMY_SLUG
from tests.ui.stub_helpers import install_streamlit_stub

PAGES_DIR = Path(__file__).resolve().parents[2] / "src" / "ui" / "pages"
MODULE_PREFIX = "ui.pages"

PAGE_MODULES = sorted(
    f"{MODULE_PREFIX}.{path.stem}"
    for path in PAGES_DIR.glob("*.py")
    if path.suffix == ".py" and path.stem != "__init__"
)


@pytest.mark.parametrize("module_name", PAGE_MODULES)
def test_ui_pages_import_stub(module_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Importa tutte le pagine UI con PREVIEW_MODE=stub per intercettare wiring mancante."""

    st_stub = install_streamlit_stub(monkeypatch)
    st_stub.session_state.setdefault("active_slug", DUMMY_SLUG)
    st_stub.query_params["slug"] = DUMMY_SLUG
    monkeypatch.setenv("PREVIEW_MODE", "stub")
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("PREVIEW_LOG_DIR", str(tmp_path / "preview_logs"))
    monkeypatch.chdir(tmp_path)

    sys.modules.pop(module_name, None)
    try:
        importlib.import_module(module_name)
    except RuntimeError as exc:
        if str(exc) != "stop requested":
            raise
    except InvalidSlug:
        # Alcune pagine richiedono slug attivo; l'import può validare e fallire senza side-effect.
        pass
    except TypeError as exc:
        if "Streamlit fragment" not in str(exc):
            raise
