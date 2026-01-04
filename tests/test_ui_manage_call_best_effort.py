# SPDX-License-Identifier: GPL-3.0-only
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

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
    fake_clients_store.get_ui_state_path = lambda: Path("ui_state.json")  # type: ignore[attr-defined]
    fake_clients_store.set_state = lambda *_a, **_k: True  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ui.chrome", fake_chrome)
    monkeypatch.setitem(sys.modules, "ui.clients_store", fake_clients_store)

    base_dir = tmp_path / "timmy-kb-dummy"
    raw_dir = base_dir / "raw"
    semantic_dir = base_dir / "semantic"
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    fake_workspace = types.ModuleType("ui.utils.workspace")
    fake_workspace.get_ui_workspace_layout = lambda *_a, **_k: SimpleNamespace(
        base_dir=base_dir,
        raw_dir=raw_dir,
        semantic_dir=semantic_dir,
    )
    fake_workspace.count_pdfs_safe = lambda *_a, **_k: 0
    monkeypatch.setitem(sys.modules, "ui.utils.workspace", fake_workspace)

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
        slug="dummy",
        require_env=True,
        sig_only="X",
    )

    assert result == ("X", "dummy", True)
