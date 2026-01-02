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


class _FakeClient:
    def __init__(self, text: str):
        self._text = text
        self.responses = self

    def create(self, *args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(self._text)


class _NoResponsesClient:
    pass


class _ResponsesWithoutCreate:
    responses = object()


class _FallbackClient:
    def __init__(self, text: str, reject_order: list[str]):
        self._text = text
        self._reject_order = reject_order
        self.calls: list[dict[str, object]] = []
        self.responses = self

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        for key in self._reject_order:
            if key in kwargs:
                raise TypeError(f"create() got an unexpected keyword argument '{key}'")
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


def test_run_json_model_missing_responses_raises() -> None:
    client = _NoResponsesClient()
    with pytest.raises(ConfigError) as exc:
        run_json_model(
            model="stub",
            messages=[{"role": "user", "content": "hi"}],
            client=client,
        )
    assert "Client OpenAI non supporta l'API Responses." in str(exc.value)


def test_run_json_model_responses_without_create_raises() -> None:
    client = _ResponsesWithoutCreate()
    with pytest.raises(ConfigError) as exc:
        run_json_model(
            model="stub",
            messages=[{"role": "user", "content": "hi"}],
            client=client,
        )
    assert "Client OpenAI non supporta l'API Responses." in str(exc.value)


def test_run_json_model_fallback_removes_response_format_only() -> None:
    client = _FallbackClient('{"ok": true}', reject_order=["response_format"])
    result = run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        client=client,
    )
    assert result.data["ok"] is True
    assert len(client.calls) == 2
    assert "response_format" in client.calls[0]
    assert "metadata" in client.calls[0]
    assert "response_format" not in client.calls[1]
    assert "metadata" in client.calls[1]


def test_run_json_model_fallback_removes_response_format_and_metadata() -> None:
    client = _FallbackClient('{"ok": true}', reject_order=["response_format", "metadata"])
    result = run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        client=client,
    )
    assert result.data["ok"] is True
    assert len(client.calls) == 3
    assert "response_format" in client.calls[0]
    assert "metadata" in client.calls[0]
    assert "response_format" not in client.calls[1]
    assert "metadata" in client.calls[1]
    assert "response_format" not in client.calls[2]
    assert "metadata" not in client.calls[2]


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
