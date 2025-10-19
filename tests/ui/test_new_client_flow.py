from __future__ import annotations

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
            def update(self, *_s_args: Any, **_s_kwargs: Any) -> None:
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


def test_mirror_repo_config_preserves_client_fields(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StreamlitStub()
    monkeypatch.setitem(sys.modules, "streamlit", stub)

    import src.ui.pages.new_client as new_client

    slug = "acme"
    template_root = tmp_path
    (template_root / "config").mkdir(parents=True, exist_ok=True)
    (template_root / "config" / "config.yaml").write_text("client_name: Template\nfoo: bar\n", encoding="utf-8")
    client_cfg_dir = template_root / "output" / f"timmy-kb-{slug}" / "config"
    client_cfg_dir.mkdir(parents=True, exist_ok=True)
    (client_cfg_dir / "config.yaml").write_text("client_name: ACME\n", encoding="utf-8")

    monkeypatch.setattr(new_client, "_repo_root", lambda: template_root)

    original = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")

    new_client._mirror_repo_config_into_client(slug, pdf_bytes=b"pdf")

    updated = (client_cfg_dir / "config.yaml").read_text(encoding="utf-8")
    assert "client_name: ACME" in updated
    assert updated.count("client_name") == original.count("client_name")
    assert "foo: bar" in updated
