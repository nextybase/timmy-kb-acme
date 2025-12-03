# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import sys
import types
from typing import Any, Dict

import pytest

from ai import client_factory
from pipeline.exceptions import ConfigError


def test_make_openai_client_requires_modern_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # pragma: allowlist secret
    monkeypatch.setattr(client_factory, "_load_settings", lambda: None)

    class LegacyOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")

    dummy_module = types.ModuleType("openai")
    dummy_module.OpenAI = LegacyOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", dummy_module)

    with pytest.raises(ConfigError) as excinfo:
        client_factory.make_openai_client()

    assert "openai" in str(excinfo.value).lower()
    assert "aggiorna" in str(excinfo.value).lower()


def test_make_openai_client_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")  # pragma: allowlist secret
    monkeypatch.setenv("OPENAI_BASE_URL", "api.nexty.ai")
    monkeypatch.setenv("OPENAI_PROJECT", "alpha")
    settings_stub = types.SimpleNamespace(
        openai_settings=types.SimpleNamespace(timeout=30, max_retries=5, http2_enabled=True)
    )
    monkeypatch.setattr(client_factory, "_load_settings", lambda: settings_stub)

    captured_kwargs: Dict[str, Any] = {}

    class ModernOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    dummy_module = types.ModuleType("openai")
    dummy_module.OpenAI = ModernOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", dummy_module)

    client_factory.make_openai_client()

    assert captured_kwargs["api_key"] == "secret"  # pragma: allowlist secret
    assert captured_kwargs["default_headers"] == {"OpenAI-Beta": "assistants=v2"}
    assert captured_kwargs["base_url"] == "https://api.nexty.ai/v1"
    assert captured_kwargs["project"] == "alpha"
    assert captured_kwargs["timeout"] == 30.0
    assert captured_kwargs["max_retries"] == 5
    assert captured_kwargs["http2"] is True
