# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from tests.ui.stub_helpers import install_streamlit_stub


def _load_landing(monkeypatch: pytest.MonkeyPatch) -> Tuple[Any, Any]:
    """Ricarica ui.landing_slug usando lo streamlit stub e header neutro."""
    st_stub = install_streamlit_stub(monkeypatch)
    import ui.utils.branding as branding

    monkeypatch.setattr(branding, "render_brand_header", lambda **_kwargs: None, raising=False)

    sys.modules.pop("ui.landing_slug", None)
    module = importlib.import_module("ui.landing_slug")

    monkeypatch.setattr(module, "st", importlib.import_module("streamlit"), raising=False)
    return module, st_stub


def test_render_header_form_returns_slug_and_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _load_landing(monkeypatch)
    st_stub.session_state["ls_slug"] = "dummy"
    st_stub.register_button_sequence("Verifica cliente", [True])
    monkeypatch.setattr(module, "get_bool", lambda *_args, **_kwargs: False, raising=False)

    slug_input, verify_clicked = module.render_header_form("dummy", log=None)

    assert slug_input == "dummy"
    assert verify_clicked is True


def test_handle_verify_workflow_invalid_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _load_landing(monkeypatch)

    slug, state_dict, submitted, has_error = module.handle_verify_workflow(
        slug_state="",
        slug_input="bad slug",
        verify_clicked=True,
        vision_state=None,
    )

    assert slug == ""
    assert state_dict == {}
    assert submitted is False
    assert has_error is True
    assert any("Slug non valido" in msg for msg in st_stub.error_messages)


def test_handle_verify_workflow_valid_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _load_landing(monkeypatch)

    slug, state_dict, submitted, has_error = module.handle_verify_workflow(
        slug_state="",
        slug_input="acme-team",
        verify_clicked=True,
        vision_state=None,
    )

    assert slug == "acme-team"
    assert submitted is True
    assert has_error is False
    assert state_dict["slug"] == "acme-team"
    assert st_stub.session_state.get("ui.slug") == "acme-team"
    assert isinstance(st_stub.session_state.get("ui.vision_workflow"), dict)


def test_workspace_summary_existing_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module, st_stub = _load_landing(monkeypatch)
    workspace_dir = tmp_path / "dummy"
    workspace_dir.mkdir()
    vision_state: Dict[str, Any] = {"verified": False, "workspace_created": False, "client_name": "Dummy"}

    called: Dict[str, Tuple[str, str]] = {}

    def _fake_enter(slug: str, fallback: str) -> Tuple[bool, str, str]:
        called["args"] = (slug, fallback)
        return True, slug, fallback or slug

    monkeypatch.setattr(
        module,
        "_workspace_dir_for",
        lambda _slug, *, layout=None: workspace_dir,
        raising=False,
    )
    monkeypatch.setattr(module, "_enter_existing_workspace", _fake_enter, raising=False)

    result = module.render_workspace_summary("dummy", vision_state, slug_submitted=True, log=None)

    assert result == (True, "dummy", "Dummy")
    assert called["args"] == ("dummy", "Dummy")
    assert st_stub.session_state.get("ui.vision_workflow") is None


def test_workspace_summary_marks_new_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module, st_stub = _load_landing(monkeypatch)
    monkeypatch.setattr(
        module,
        "_workspace_dir_for",
        lambda _slug, *, layout=None: tmp_path / "missing",
        raising=False,
    )
    vision_state: Dict[str, Any] = {
        "verified": False,
        "workspace_created": False,
        "client_name": "",
        "needs_creation": False,
    }

    ok, slug, client_name = module.render_workspace_summary("dummy", vision_state, slug_submitted=True, log=None)

    assert ok is False
    assert slug == "dummy"
    assert client_name == ""
    assert vision_state["verified"] is True
    assert vision_state["needs_creation"] is True
    assert st_stub.session_state.get("ui.vision_workflow") == vision_state
    assert any("Cliente nuovo" in msg for msg in st_stub.success_messages)


def test_workspace_summary_requires_verification_before_form(monkeypatch: pytest.MonkeyPatch) -> None:
    module, st_stub = _load_landing(monkeypatch)
    vision_state: Dict[str, Any] = {}

    ok, slug, client_name = module.render_workspace_summary("dummy", vision_state, slug_submitted=False, log=None)

    assert ok is False
    assert slug == "dummy"
    assert client_name == ""
    assert st_stub.session_state.get("ui.vision_workflow") is None
