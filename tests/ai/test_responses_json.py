# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai.responses import (
    ConfigError,
    _diagnose_json_schema_format,
    _normalize_response_format,
    _parse_json_payload,
    run_json_model,
)
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe


class _FakeResponse:
    def __init__(self, text: str):
        self.output_text = text
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


class _TypeErrorClient:
    responses = SimpleNamespace()

    def __init__(self) -> None:
        self.responses = self

    def create(self, **_kwargs: object) -> _FakeResponse:
        raise TypeError("create() got an unexpected keyword argument 'response_format'")


def _load_vision_schema() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = ensure_within_and_resolve(
        repo_root, repo_root / "src" / "ai" / "schemas" / "VisionOutput.schema.json"
    )
    raw = read_text_safe(repo_root, schema_path, encoding="utf-8")
    return json.loads(raw)


def _find_diagnostics_record(caplog: pytest.CaptureFixture[str]) -> logging.LogRecord:
    for record in caplog.records:
        if getattr(record, "event", "") == "ai.responses.json_schema_diagnostics":
            return record
        if record.getMessage() == "ai.responses.json_schema_diagnostics":
            return record
    raise AssertionError("ai.responses.json_schema_diagnostics record not found")


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


def test_run_json_model_type_error_raises() -> None:
    client = _TypeErrorClient()
    with pytest.raises(ConfigError):
        run_json_model(
            model="stub",
            messages=[{"role": "user", "content": "hi"}],
            client=client,
        )


def test_parse_json_with_fences_raises() -> None:
    text = '```json\n{"foo": 1}\n```'
    with pytest.raises(json.JSONDecodeError):
        _parse_json_payload(text)


def test_run_json_model_invalid_json_raises() -> None:
    client = _FakeClient("not json")
    with pytest.raises(ConfigError):
        run_json_model(
            model="stub",
            messages=[{"role": "user", "content": "hi"}],
            client=client,
        )


def test_normalize_response_format_json_schema_flattens() -> None:
    payload = {
        "type": "json_schema",
        "json_schema": {"name": "X", "schema": {"type": "object"}, "strict": True},
    }
    normalized = _normalize_response_format(payload)
    assert normalized["type"] == "json_schema"
    assert normalized["name"] == "X"
    assert normalized["schema"] == {"type": "object"}
    assert normalized["strict"] is True
    assert "json_schema" not in normalized


def test_normalize_response_format_json_schema_missing_name_raises() -> None:
    payload = {"type": "json_schema", "json_schema": {"schema": {"type": "object"}, "strict": True}}
    with pytest.raises(ConfigError) as exc:
        _normalize_response_format(payload)
    assert exc.value.code == "responses.request.invalid"
    assert exc.value.component == "responses"


def test_normalize_response_format_non_json_schema_passthrough() -> None:
    payload = {"type": "json_object"}
    assert _normalize_response_format(payload) == payload


def test_diagnostics_required_minus_properties_empty_for_vision_schema() -> None:
    schema = _load_vision_schema()
    diagnostics = _diagnose_json_schema_format({"type": "json_schema", "schema": schema})
    assert diagnostics["required_minus_properties"] == []


def test_diagnostics_detects_map_like_paths_for_vision_schema() -> None:
    schema = _load_vision_schema()
    diagnostics = _diagnose_json_schema_format({"type": "json_schema", "schema": schema})
    assert diagnostics["map_like_paths"] == []


def test_vision_schema_documents_min_items() -> None:
    schema = _load_vision_schema()
    areas_docs = (
        schema.get("properties", {}).get("areas", {}).get("items", {}).get("properties", {}).get("documents", {})
    )
    identity_docs = (
        schema.get("properties", {})
        .get("system_folders", {})
        .get("properties", {})
        .get("identity", {})
        .get("properties", {})
        .get("documents", {})
    )
    assert areas_docs.get("minItems") == 1
    assert identity_docs.get("minItems") == 1


def test_run_json_model_emits_json_schema_diagnostics_log(caplog) -> None:
    caplog.set_level(logging.INFO, logger="ai.responses")
    client = _FakeClient('{"ok": true}')
    run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "VisionOutput_v2",
                "schema": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
                "strict": True,
            },
        },
        client=client,
    )
    record = _find_diagnostics_record(caplog)
    assert record.root_properties_count == 1
    assert record.root_required_count == 1
    assert record.required_minus_properties == []
    assert record.properties_minus_required == []
    assert record.name_present is True


def test_debug_runtime_dump_writes_run_specific_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DEBUG_RUNTIME", "1")
    monkeypatch.setattr("ai.responses.get_repo_root", lambda allow_env=False: tmp_path)
    captured: dict[str, Any] = {}

    def fake_write_text(path: Path, text: str, encoding: str) -> None:
        captured["path"] = path
        captured["text"] = text

    monkeypatch.setattr("ai.responses.safe_write_text", fake_write_text)
    client = _FakeClient('{"ok": true}')
    run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "X", "schema": {"type": "object"}, "strict": True},
        },
        invocation={"run_id": "run-123"},
        client=client,
    )

    assert "path" in captured
    expected_dir = tmp_path / "output" / "debug" / "responses" / "run-123"
    assert str(captured["path"]).endswith(str(expected_dir / "vision_schema_sent.json"))


def test_debug_runtime_skips_dump_without_run_id(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DEBUG_RUNTIME", "1")
    monkeypatch.setattr(
        "ai.responses.safe_write_text", lambda *args, **kwargs: pytest.fail("dump should not be written")
    )
    caplog.set_level(logging.WARNING, logger="ai.responses")
    client = _FakeClient('{"ok": true}')

    run_json_model(
        model="stub",
        messages=[{"role": "user", "content": "hi"}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "X", "schema": {"type": "object"}, "strict": True},
        },
        invocation={"component": "test"},
        client=client,
    )

    assert any(record.message == "ai.responses.json_schema_dump_skipped_missing_run_id" for record in caplog.records)
