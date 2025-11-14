# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import vision_alignment_check as vac


class _DummyOpenAI:
    def __init__(self, **kwargs: Any) -> None:
        self.responses = self
        self.kwargs = kwargs
        self.last_request: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.last_request = kwargs
        return SimpleNamespace(output=[], id="run-id", model=kwargs["model"])


@pytest.mark.parametrize(
    "strict_output,expected_format",
    [
        (True, "json_schema"),
        (False, "text"),
    ],
)
def test_response_format_matches_strict_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strict_output: bool,
    expected_format: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "assistant-id")
    monkeypatch.setattr(vac, "_load_env_and_sanitize", lambda: None)
    monkeypatch.setattr(
        "semantic.vision_provision._load_vision_schema",
        lambda: {"type": "object", "properties": {}},
    )

    vision_settings = SimpleNamespace(strict_output=strict_output, use_kb=False)
    stub_settings = SimpleNamespace(
        vision_settings=vision_settings,
        vision_model="gpt-test",
        vision_assistant_env="OBNEXT_ASSISTANT_ID",
        openai_settings=SimpleNamespace(timeout=1, max_retries=1, http2_enabled=False),
    )

    class SettingsLoader:
        @staticmethod
        def load(root: str | Path) -> SimpleNamespace:  # type: ignore[name-defined]
            return stub_settings

    monkeypatch.setattr(vac, "PipelineSettings", SettingsLoader)

    created: list[_DummyOpenAI] = []

    def _openai_factory(**kwargs: Any) -> _DummyOpenAI:
        client = _DummyOpenAI(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("openai.OpenAI", _openai_factory)
    captured_logs: list[tuple[str, dict[str, Any]]] = []
    original_info = vac.LOGGER.info

    def _info(msg: str, *args: Any, **kwargs: Any) -> None:
        captured_logs.append((msg, kwargs))
        return original_info(msg, *args, **kwargs)

    monkeypatch.setattr(vac.LOGGER, "info", _info)

    with pytest.raises(SystemExit) as excinfo:
        vac.main()
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    output = captured.out.strip()
    result = json.loads(output)

    log_entry = next(
        (kwargs for msg, kwargs in captured_logs if msg == "vision_alignment_check.strict_output"),
        None,
    )
    assert log_entry is not None
    assert log_entry["extra"]["value"] is strict_output
    assert log_entry["extra"]["source"] == "config"
    assert result["response_format"] == expected_format
    assert result["strict_output"] is strict_output
    assert result["strict_output_source"] == "config"
    assert result["use_kb_source"] == "config"
    request = created[0].last_request
    assert request is not None
    assert ("text" in request) is strict_output


def test_strict_output_logged_default_source_when_settings_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("VISION_USE_KB", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "assistant-id")
    monkeypatch.setattr(vac, "_load_env_and_sanitize", lambda: None)
    monkeypatch.setattr(
        "semantic.vision_provision._load_vision_schema",
        lambda: {"type": "object", "properties": {}},
    )

    class BrokenSettingsLoader:
        @staticmethod
        def load(root: str | Path) -> SimpleNamespace:  # type: ignore[name-defined]
            raise RuntimeError("No config")

    monkeypatch.setattr(vac, "PipelineSettings", BrokenSettingsLoader)

    def _openai_factory(**kwargs: Any) -> _DummyOpenAI:
        client = _DummyOpenAI(**kwargs)
        return client

    monkeypatch.setattr("openai.OpenAI", _openai_factory)
    captured_logs: list[tuple[str, dict[str, Any]]] = []
    original_info = vac.LOGGER.info

    def _info(msg: str, *args: Any, **kwargs: Any) -> None:
        captured_logs.append((msg, kwargs))
        return original_info(msg, *args, **kwargs)

    monkeypatch.setattr(vac.LOGGER, "info", _info)

    with pytest.raises(SystemExit) as excinfo:
        vac.main()
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    log_entry = next(
        (kwargs for msg, kwargs in captured_logs if msg == "vision_alignment_check.strict_output"),
        None,
    )
    assert log_entry is not None
    assert log_entry["extra"]["value"] is True
    assert log_entry["extra"]["source"] == "default"
    result = json.loads(captured.out.strip())
    assert result["strict_output"] is True
    assert result["strict_output_source"] == "default"
    assert result["use_kb_source"] == "env"
