# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.capabilities.vision import iter_available_vision_providers, load_vision_bindings
from pipeline.exceptions import CapabilityUnavailableError


def test_load_vision_bindings_uses_candidate(monkeypatch):
    calls: list[str] = []

    def fake_import(name: str):
        calls.append(name)
        if name == "custom.module":
            return SimpleNamespace(
                HaltError=ValueError,
                provision_from_vision_with_config=lambda **kwargs: {"mapping": "ok"},
                prepare_assistant_input_with_config=lambda **kwargs: "prompt",
                provision_from_vision_yaml_with_config=None,
                prepare_assistant_input_from_yaml_with_config=None,
            )
        raise ImportError("missing")

    monkeypatch.setattr("pipeline.capabilities.vision.import_module", fake_import)
    bindings = load_vision_bindings(candidates=("custom.module",))
    assert bindings.halt_error is ValueError
    assert bindings.prepare_with_config() == "prompt"
    assert bindings.provision_with_config() == {"mapping": "ok"}
    assert calls == ["custom.module"]


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
    with pytest.raises(CapabilityUnavailableError):
        list(iter_available_vision_providers(candidates=("missing.one",)))
