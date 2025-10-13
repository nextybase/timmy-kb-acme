from __future__ import annotations

import importlib
import logging
import shutil
import sys
import types
from pathlib import Path
from typing import Any

import pytest


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.button_returns: dict[str, bool] = {}
        self.success_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.error_messages: list[str] = []
        self.html_calls: list[str] = []
        self.rerun_called = 0

    def subheader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def text_input(self, _label: str, *, value: str = "", **_kwargs: Any) -> str:
        return value

    def file_uploader(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def button(self, label: str, *_args: Any, **_kwargs: Any) -> bool:
        return self.button_returns.get(label, False)

    def warning(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.warning_messages.append(message)

    def success(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.success_messages.append(message)

    def error(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.error_messages.append(message)

    def status(self, *_args: Any, **_kwargs: Any):
        class _Status:
            def __enter__(self) -> "_Status":
                return self

            def __exit__(self, *_exc: Any) -> bool:
                return False

            def update(self, *_args: Any, **_kwargs: Any) -> None:
                return None

        return _Status()

    def progress(self, *_args: Any, **_kwargs: Any):
        class _Progress:
            def progress(self, *_p_args: Any, **_p_kwargs: Any) -> None:
                return None

        return _Progress()

    def empty(self, *_args: Any, **_kwargs: Any):
        class _Empty:
            def markdown(self, *_m_args: Any, **_m_kwargs: Any) -> None:
                return None

        return _Empty()

    def html(self, markup: str, *_args: Any, **_kwargs: Any) -> None:
        self.html_calls.append(markup)

    def stop(self) -> None:
        return None

    def rerun(self) -> None:
        self.rerun_called += 1


@pytest.fixture
def _prepare_workspace():
    slug = "acme"
    project_root = Path(__file__).resolve().parents[2]
    client_root = project_root / "output" / f"timmy-kb-{slug}"
    if client_root.exists():
        shutil.rmtree(client_root)
    (client_root / "semantic").mkdir(parents=True, exist_ok=True)
    (client_root / "semantic" / "semantic_mapping.yaml").write_text("version: 1\n", encoding="utf-8")
    (client_root / "semantic" / "cartelle_raw.yaml").write_text("version: 1\n", encoding="utf-8")

    try:
        yield slug, client_root
    finally:
        if client_root.exists():
            shutil.rmtree(client_root)


def _setup_common_mocks(monkeypatch: pytest.MonkeyPatch, stub: _StreamlitStub) -> None:
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    import ui.chrome as chrome

    monkeypatch.setattr(chrome, "header", lambda *_a, **_k: None)
    monkeypatch.setattr(chrome, "sidebar", lambda *_a, **_k: None)

    import ui.clients_store as clients_store

    state_log: list[tuple[str, str]] = []

    def _fake_set_state(slug: str, state: str) -> None:
        state_log.append((slug, state))

    monkeypatch.setattr(clients_store, "set_state", _fake_set_state, raising=True)
    upsert_log: list[Any] = []
    monkeypatch.setattr(clients_store, "upsert_client", lambda entry: upsert_log.append(entry), raising=True)

    stub._state_log = state_log  # type: ignore[attr-defined]
    stub._upsert_log = upsert_log  # type: ignore[attr-defined]

    fake_drive_module = types.ModuleType("ui.services.drive_runner")
    monkeypatch.setitem(sys.modules, "ui.services.drive_runner", fake_drive_module)


def test_local_fallback_promotes_state_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _prepare_workspace
) -> None:
    slug, client_root = _prepare_workspace

    stub = _StreamlitStub()
    stub.button_returns = {"Inizializza Workspace": False, "Apri workspace": True}
    stub.session_state = {
        "new_client.phase": "init",
        "new_client.slug": slug,
        "client_name": "ACME",
    }

    monkeypatch.setenv("UI_ALLOW_LOCAL_ONLY", "true")
    _setup_common_mocks(monkeypatch, stub)
    sys.modules.pop("src.ui.pages.new_client", None)

    import src.ui.pages.new_client as new_client

    stub.session_state["new_client.phase"] = new_client.UI_PHASE_READY_TO_OPEN
    stub.session_state["client_name"] = "ACME"

    caplog.clear()
    with caplog.at_level(logging.INFO):
        importlib.reload(new_client)

    assert stub.session_state.get("new_client.phase") == new_client.UI_PHASE_PROVISIONED
    assert stub.session_state.get("client_name") == "ACME"
    assert any("Drive non configurato" in msg for msg in stub.success_messages)
    assert any(record.getMessage() == "ui.wizard.local_fallback" for record in caplog.records)
    assert ("acme", "pronto") in getattr(stub, "_state_log")


def test_local_fallback_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch, _prepare_workspace) -> None:
    slug, _client_root = _prepare_workspace

    stub = _StreamlitStub()
    stub.button_returns = {"Inizializza Workspace": False, "Apri workspace": True}
    stub.session_state = {
        "new_client.phase": "init",
        "new_client.slug": slug,
        "client_name": "ACME",
    }

    monkeypatch.setenv("UI_ALLOW_LOCAL_ONLY", "false")
    _setup_common_mocks(monkeypatch, stub)
    sys.modules.pop("src.ui.pages.new_client", None)

    import src.ui.pages.new_client as new_client

    stub.session_state["new_client.phase"] = new_client.UI_PHASE_READY_TO_OPEN

    importlib.reload(new_client)

    assert stub.session_state.get("new_client.phase") == new_client.UI_PHASE_READY_TO_OPEN
    assert stub.success_messages == []
    assert stub.warning_messages
    assert getattr(stub, "_state_log") == []
