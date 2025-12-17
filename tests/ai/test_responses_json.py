# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.responses import ConfigError, _parse_json_payload, run_json_model


class _FakeResponse:
    def __init__(self, text: str):
        self.output = [
            SimpleNamespace(
                type="output_text",
                text=SimpleNamespace(value=text),
            )
        ]
        self.status = "completed"
        self.id = "fake"
        self.output_text = text


class _FakeClient:
    def __init__(self, text: str):
        self._text = text
        self.responses = self

    def create(self, *args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(self._text)


def test_run_json_model_uses_client_without_make(monkeypatch) -> None:
    called = {"make": False}

    def fake_make() -> None:
        called["make"] = True
        raise AssertionError("make_openai_client should not be called when client provided")

    monkeypatch.setattr("ai.responses.make_openai_client", fake_make)
    client = _FakeClient('{"parsed": true}')
    result = run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
        client=client,
    )
    assert result.data["parsed"] is True
    assert called["make"] is False


def test_parse_json_with_fences() -> None:
    text = '```json\n{"foo": 1}\n```'
    payload = _parse_json_payload(text)
    assert payload == {"foo": 1}


def test_run_json_model_invalid_json_raises() -> None:
    client = _FakeClient("not json")
    with pytest.raises(ConfigError):
        run_json_model(
            model="stub",
            messages=[{"role": "user", "content": "hi"}],
            client=client,
        )
