# SPDX-License-Identifier: GPL-3.0-only
import importlib
import logging
import sys
import types
from pathlib import Path

import pytest
from tests.ui.test_manage_modal_save import _build_streamlit_stub


@pytest.fixture(name="manage_module")
def manage_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module, submodules = _build_streamlit_stub(save_button_pressed=False)
    monkeypatch.setitem(sys.modules, "streamlit", module)
    for name, mod in submodules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    fake_chrome = types.ModuleType("ui.chrome")
    fake_chrome.render_chrome_then_require = lambda **_kwargs: "dummy"  # type: ignore[attr-defined]
    fake_clients_store = types.ModuleType("ui.clients_store")
    fake_clients_store.get_state = lambda slug: "ready"  # type: ignore[attr-defined]
    fake_clients_store.get_all = lambda: []  # type: ignore[attr-defined]
    fake_clients_store.get_ui_state_path = lambda: tmp_path / "ui_state.json"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ui.chrome", fake_chrome)
    monkeypatch.setitem(sys.modules, "ui.clients_store", fake_clients_store)

    sys.modules.pop("ui.pages.manage", None)
    manage = importlib.import_module("ui.pages.manage")
    try:
        yield manage
    finally:
        sys.modules.pop("ui.pages.manage", None)


def test_load_clients_logs_warning_when_broken(caplog, monkeypatch, tmp_path, manage_module):
    caplog.set_level(logging.WARNING)
    clients_path = tmp_path / "clients.yaml"
    clients_path.write_text("slug: dummy", encoding="utf-8")

    monkeypatch.setattr(manage_module, "_clients_db_path", lambda: Path(clients_path))

    monkeypatch.setattr(
        manage_module,
        "get_clients",
        lambda: (_ for _ in ()).throw(RuntimeError("bad yaml")),
    )

    assert manage_module._load_clients() == []
    assert any("ui.manage.clients.load_error" in record.message for record in caplog.records)
