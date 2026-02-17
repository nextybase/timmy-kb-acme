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


def test_preflight_attestation_check_degrades_on_unexpected_error(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "ui.preflight", raising=False)
    mod = importlib.import_module("ui.preflight")
    monkeypatch.setattr(mod, "validate_env_attestation", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    checks = mod._collect_attestation_checks()
    assert len(checks) == 1
    name, ok, hint = checks[0]
    assert name == "Environment attestation"
    assert ok is False
    assert "Check attestazione fallito in modo inatteso." in hint
