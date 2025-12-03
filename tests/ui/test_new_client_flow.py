# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import logging
import shutil
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from tests.ui.streamlit_stub import StreamlitStub
from tests.ui.test_manage_probe_raw import register_streamlit_runtime


def _make_st() -> StreamlitStub:
    st = StreamlitStub()
    st.register_button_sequence("Inizializza Workspace", [True])
    st.register_button_sequence("btn_init_ws", [True])
    return st


def _make_pdf_stub(payload: bytes) -> Any:
    class _Pdf:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def getvalue(self) -> bytes:
            return self._data

    return _Pdf(payload)


def test_init_workspace_skips_drive_when_helper_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    slug = "dummy"
    monkeypatch.chdir(tmp_path)
    client_root = tmp_path / "output" / f"timmy-kb-{slug}"
    if client_root.exists():
        shutil.rmtree(client_root)

    stub = _make_st()
    stub.session_state = {"new_client.phase": "init", "new_client.slug": "", "client_name": ""}
    orig_text_input = stub.text_input
    stub.text_input = lambda label, **kwargs: (
        "dummy" if "Slug" in label else kwargs.get("value", "")
    ) or orig_text_input(label, **kwargs)
    stub.file_uploader = lambda *_args, **_kwargs: _make_pdf_stub(b"%PDF-1.4")

    settings_stub = types.SimpleNamespace(ui_allow_local_only=True)
    monkeypatch.setattr("pipeline.settings.Settings.load", lambda *_a, **_k: settings_stub)
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)

    fake_drive_module = types.ModuleType("ui.services.drive_runner")
    monkeypatch.setitem(sys.modules, "ui.services.drive_runner", fake_drive_module)

    import pre_onboarding as pre_onboarding

    def _fake_bootstrap(slug: str, *, client_name: str | None, vision_statement_pdf: bytes | None) -> None:
        base = client_root
        (base / "config").mkdir(parents=True, exist_ok=True)
        (base / "config" / "config.yaml").write_text("client_name: Dummy\n", encoding="utf-8")
        (base / "semantic").mkdir(parents=True, exist_ok=True)
        if vision_statement_pdf:
            (base / "config" / "VisionStatement.pdf").write_bytes(vision_statement_pdf)

    monkeypatch.setattr(pre_onboarding, "ensure_local_workspace_for_ui", _fake_bootstrap, raising=True)

    import ui.services.vision_provision as vision_mod

    def _fake_run_vision(ctx: Any, *, slug: str, pdf_path: Path, logger: Any | None = None, **_: Any) -> None:
        semantic_dir = Path(ctx.base_dir) / "semantic"
        semantic_dir.mkdir(parents=True, exist_ok=True)
        (semantic_dir / "semantic_mapping.yaml").write_text("version: 1\n", encoding="utf-8")
        (semantic_dir / "cartelle_raw.yaml").write_text("version: 1\n", encoding="utf-8")

    monkeypatch.setattr(vision_mod, "run_vision", _fake_run_vision, raising=True)

    sys.modules.pop("ui.utils.status", None)
    from contextlib import contextmanager

    import ui.utils.status as status_mod

    @contextmanager
    def _guard(*_a: Any, **_k: Any):
        with stub.status() as status:
            yield status

    monkeypatch.setattr(status_mod, "status_guard", _guard, raising=True)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        sys.modules.pop("src.ui.pages.new_client", None)
        import ui.pages.new_client as new_client

        importlib.reload(new_client)

    try:
        assert stub.success_messages is not None
        assert not stub.error_messages
        assert stub.session_state.get("new_client.phase") == "ready_to_open"
        assert stub.session_state.get("new_client.slug") == slug
        assert any("ui.drive.provisioning_skipped" in record.getMessage() for record in caplog.records)
    finally:
        if client_root.exists():
            shutil.rmtree(client_root)


def test_ui_allow_local_only_reloads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [True, False]
    last_flag = {"value": False}

    def _fake_load(*_a: Any, **_k: Any) -> types.SimpleNamespace:
        if values:
            last_flag["value"] = values.pop(0)
        return types.SimpleNamespace(ui_allow_local_only=last_flag["value"])

    monkeypatch.setattr("pipeline.settings.Settings.load", _fake_load, raising=True)
    import ui.pages.new_client as new_client

    assert new_client.ui_allow_local_only_enabled() is True
    assert new_client.ui_allow_local_only_enabled() is False
