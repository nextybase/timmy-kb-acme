import importlib
import sys
import types
from pathlib import Path

import pytest

from tests.ui.test_manage_modal_save import _build_streamlit_stub


@pytest.fixture(name="manage_module")
def manage_module(monkeypatch: pytest.MonkeyPatch):
    module, submodules = _build_streamlit_stub(save_button_pressed=False)
    monkeypatch.setitem(sys.modules, "streamlit", module)
    for name, mod in submodules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    fake_chrome = types.ModuleType("ui.chrome")
    fake_chrome.render_chrome_then_require = lambda **_kwargs: "acme"  # type: ignore[attr-defined]
    fake_clients_store = types.ModuleType("ui.clients_store")
    fake_clients_store.get_state = lambda slug: "ready"  # type: ignore[attr-defined]
    fake_clients_store.get_all = lambda: []  # type: ignore[attr-defined]
    fake_clients_store.get_ui_state_path = lambda: Path("ui_state.json")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ui.chrome", fake_chrome)
    monkeypatch.setitem(sys.modules, "ui.clients_store", fake_clients_store)

    sys.modules.pop("ui.pages.manage", None)
    manage = importlib.import_module("ui.pages.manage")
    try:
        yield manage
    finally:
        sys.modules.pop("ui.pages.manage", None)


def test_call_best_effort_signature_binding(manage_module):
    def fn_new(sig_only, slug, require_env=False):
        return (sig_only, slug, require_env)

    result = manage_module._call_best_effort(
        fn_new,
        slug="acme",
        require_env=True,
        sig_only="X",
    )

    assert result == ("X", "acme", True)
