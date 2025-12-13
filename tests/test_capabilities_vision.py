# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

from pipeline.capabilities.vision import iter_available_vision_providers, load_vision_bindings


def test_load_vision_bindings_uses_candidate(monkeypatch):
    calls: list[str] = []

    def fake_import(name: str):
        calls.append(name)
        if name == "custom.module":
            return SimpleNamespace(
                HaltError=ValueError,
                provision_from_vision=lambda **kwargs: {"mapping": "ok"},
                prepare_assistant_input=lambda **kwargs: "prompt",
                provision_from_vision_yaml=None,
                prepare_assistant_input_from_yaml=None,
            )
        raise ImportError("missing")

    monkeypatch.setattr("pipeline.capabilities.vision.import_module", fake_import)
    bindings = load_vision_bindings(candidates=("custom.module",))
    assert bindings.halt_error is ValueError
    assert bindings.prepare() == "prompt"
    assert calls == ["custom.module"]


def test_load_vision_bindings_fallback(monkeypatch):
    def always_fail(name: str):
        raise ImportError("nope")

    monkeypatch.setattr("pipeline.capabilities.vision.import_module", always_fail)
    bindings = load_vision_bindings(candidates=("missing.module",))
    assert bindings.halt_error.__name__ == "HaltError"
    assert "Import fallito: missing.module" in bindings.diagnostics


def test_iter_available_vision_providers(monkeypatch):
    seen: list[str] = []

    class FakeModule:
        pass

    def fake_import(name: str):
        seen.append(name)
        if name == "custom.ok":
            return FakeModule()
        raise ImportError()

    monkeypatch.setattr("pipeline.capabilities.vision.import_module", fake_import)
    result = list(iter_available_vision_providers(candidates=("custom.missing", "custom.ok")))
    assert seen == ["custom.missing", "custom.ok"]
    assert isinstance(result[0], FakeModule)


def test_iter_available_vision_providers_none(monkeypatch):
    def always_fail(name: str):
        raise ImportError()

    monkeypatch.setattr("pipeline.capabilities.vision.import_module", always_fail)
    assert list(iter_available_vision_providers(candidates=("missing.one",))) == []
