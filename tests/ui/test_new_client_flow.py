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

from pipeline.workspace_layout import WorkspaceLayout
from tests.ui.streamlit_stub import StreamlitStub
from tests.ui.test_manage_probe_normalized import register_streamlit_runtime


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
    repo_root = tmp_path / "repo-root"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    # Isola il repo root per il test: evita che le write vadano sotto l'output reale.
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))
    workspace_root = repo_root / "output" / f"timmy-kb-{slug}"

    def _ensure_semantic_assets(root: Path) -> None:
        semantic_dir = root / "semantic"
        semantic_dir.mkdir(parents=True, exist_ok=True)
        (semantic_dir / "semantic_mapping.yaml").write_text("version: 1\n", encoding="utf-8")

    stub = _make_st()
    stub.session_state = {"new_client.phase": "iniziale", "new_client.slug": "", "client_name": ""}
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

    import pipeline.workspace_bootstrap as workspace_bootstrap

    bootstrap_called: dict[str, int] = {"count": 0}

    def _fake_bootstrap(context: Any) -> WorkspaceLayout:
        bootstrap_called["count"] += 1
        base = workspace_root
        base.mkdir(parents=True, exist_ok=True)
        config_dir = base / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text("client_name: Dummy\n", encoding="utf-8")
        (base / "book").mkdir(parents=True, exist_ok=True)
        (base / "raw").mkdir(parents=True, exist_ok=True)
        (base / "semantic").mkdir(parents=True, exist_ok=True)
        (base / "logs").mkdir(parents=True, exist_ok=True)
        if isinstance(context, dict):
            slug = context.get("slug", "dummy")
        else:
            slug = getattr(context, "slug", "dummy")
            context.repo_root_dir = base
            context.base_dir = base
            context.config_path = config_dir / "config.yaml"
        return WorkspaceLayout.from_workspace(workspace=base, slug=slug)

    monkeypatch.setattr(workspace_bootstrap, "bootstrap_client_workspace", _fake_bootstrap, raising=True)

    import ui.services.vision_provision as vision_mod

    def _fake_run_vision(ctx: Any, *, slug: str, pdf_path: Path, logger: Any | None = None, **_: Any) -> None:
        _ensure_semantic_assets(workspace_root)

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

        try:
            importlib.reload(new_client)
        except RuntimeError:
            pass

    try:
        assert stub.success_messages is not None
        if stub.error_messages:
            assert stub.error_messages == [
                "Per aprire il workspace serve semantic/semantic_mapping.yaml. " "Esegui prima 'Inizializza Workspace'."
            ]
        assert stub.session_state.get("new_client.phase") == "pronto_apertura"
        assert stub.session_state.get("new_client.slug") == slug
        assert bootstrap_called["count"] == 1
        assert any("ui.drive.provisioning_skipped" in record.getMessage() for record in caplog.records)
    finally:
        if workspace_root.exists():
            shutil.rmtree(workspace_root, ignore_errors=True)


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


def test_ui_allow_local_only_settings_load_failure_stops(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = _make_st()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)
    sys.modules.pop("ui.pages.new_client", None)
    import ui.pages.new_client as new_client

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("settings load failed")

    monkeypatch.setattr(new_client.Settings, "load", _boom, raising=True)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            new_client.ui_allow_local_only_enabled()

    assert stub.error_messages
    assert any("Impossibile caricare la configurazione" in msg for msg in stub.error_messages)
    assert any("ui.new_client.settings_load_failed" in record.getMessage() for record in caplog.records)


def test_ui_allow_local_only_read_failure_stops(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub = _make_st()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    register_streamlit_runtime(monkeypatch, stub)
    sys.modules.pop("ui.pages.new_client", None)
    import ui.pages.new_client as new_client

    class _BadSettings:
        @property
        def ui_allow_local_only(self) -> bool:
            raise RuntimeError("read failed")

    monkeypatch.setattr(new_client.Settings, "load", lambda *_a, **_k: _BadSettings(), raising=True)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            new_client.ui_allow_local_only_enabled()

    assert stub.error_messages
    assert any("Impossibile leggere ui_allow_local_only" in msg for msg in stub.error_messages)
    assert any("ui.new_client.ui_allow_local_only_failed" in record.getMessage() for record in caplog.records)
