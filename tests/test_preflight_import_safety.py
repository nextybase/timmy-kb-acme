# SPDX-License-Identifier: GPL-3.0-or-later

import importlib
import sys
import types


def test_preflight_no_side_effect_import(monkeypatch) -> None:
    """Verifica che ui.preflight non carichi .env a import-time."""
    fake_state = {"called": False}

    class _FakeLoadDotenv:
        def __call__(self, override: bool = False) -> None:
            fake_state["called"] = True

    fake_dotenv = types.SimpleNamespace(load_dotenv=_FakeLoadDotenv())
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.delitem(sys.modules, "ui.preflight", raising=False)

    mod = importlib.import_module("ui.preflight")

    assert hasattr(mod, "_maybe_load_dotenv")
    assert fake_state["called"] is False  # nessuna chiamata durante l'import

    mod.run_preflight()
    assert fake_state["called"] is True  # invocato solo durante run_preflight
