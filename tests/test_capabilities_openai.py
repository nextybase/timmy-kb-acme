# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import builtins
import sys
import types

import pytest

from pipeline.capabilities import get_openai_ctor
from pipeline.capabilities import openai as openai_capability
from pipeline.exceptions import CapabilityUnavailableError


def test_get_openai_ctor_filters_missing_openai(monkeypatch):
    monkeypatch.delitem(sys.modules, "openai", raising=False)
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "openai" or name.startswith("openai."):
            raise ImportError("module missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    def fake_import_module(name: str):
        raise ImportError("module missing")

    monkeypatch.setattr(
        "pipeline.capabilities.openai.import_module",
        fake_import_module,
    )
    monkeypatch.setattr(openai_capability, "_openai_ctor", None)

    with pytest.raises(CapabilityUnavailableError, match="OpenAI capability not available"):
        get_openai_ctor()


def test_get_openai_ctor_returns_ctor_from_dummy_module(monkeypatch):
    module = types.ModuleType("openai")

    class DummyOpenAI:
        pass

    module.OpenAI = DummyOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setattr(openai_capability, "_openai_ctor", DummyOpenAI)

    ctor = get_openai_ctor()

    assert ctor is DummyOpenAI
