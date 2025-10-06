from __future__ import annotations

import sys
import types
from typing import Any

from ai import client_factory


def test_make_openai_client_fallback_on_proxy(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY_FOLDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    sentinel_http_client = object()
    call_args: list[tuple[Any, Any]] = []

    class DummyOpenAI:
        def __init__(self, *, api_key: str, http_client: Any = None, default_headers: Any = None) -> None:
            call_args.append((http_client, default_headers))
            if http_client is None:
                raise TypeError("Client.__init__() got an unexpected keyword argument 'proxies'")
            self.api_key = api_key
            self.http_client = http_client
            self.default_headers = default_headers

    dummy_module = types.ModuleType("openai")
    dummy_module.OpenAI = DummyOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", dummy_module)
    monkeypatch.setattr(client_factory, "_build_http_client", lambda: sentinel_http_client)

    client = client_factory.make_openai_client()

    assert client.api_key == "test-key"
    assert client.http_client is sentinel_http_client
    assert getattr(client, "default_headers") == {"OpenAI-Beta": "assistants=v2"}
    assert call_args == [
        (None, {"OpenAI-Beta": "assistants=v2"}),
        (sentinel_http_client, {"OpenAI-Beta": "assistants=v2"}),
    ]
