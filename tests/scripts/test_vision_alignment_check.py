# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

_VAC_PATH = ROOT / "tools" / "smoke" / "vision_alignment_check.py"
_spec = importlib.util.spec_from_file_location("vision_alignment_check", _VAC_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Impossibile caricare vision_alignment_check da {_VAC_PATH}")
vac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vac)  # type: ignore[arg-type]


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
    monkeypatch.setenv("vision-assistant-env", "assistant-id")
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
        vision_assistant_env="vision-assistant-env",
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

    assistant_log = next(
        (kwargs for msg, kwargs in captured_logs if msg == "vision_alignment_check.assistant_id"),
        None,
    )
    assert assistant_log is not None
    assert assistant_log["extra"]["value"] == "assistant-id"
    assert assistant_log["extra"]["source"] == "config"
    assert result["response_format"] == expected_format
    assert result["strict_output"] is strict_output
    assert result["strict_output_source"] == "config"
    assert result["use_kb_source"] == "config"
    assert result["assistant_id"] == "assistant-id"
    assert result["assistant_id_source"] == "config"
    assert result["assistant_env"] == "vision-assistant-env"
    assert result["assistant_env_source"] == "config"
    request = created[0].last_request
    assert request is not None
    assert "text" not in request
    assert isinstance(request.get("input"), list)
    assert request["input"][0]["role"] == "system"
    assert request["input"][0]["content"][0]["type"] == "input_text"
    assert request["input"][1]["role"] == "user"
    assert request["input"][1]["content"][0]["type"] == "input_text"


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
    assistant_log = next(
        (kwargs for msg, kwargs in captured_logs if msg == "vision_alignment_check.assistant_id"),
        None,
    )
    assert assistant_log is not None
    assert assistant_log["extra"]["source"] == "env"
    result = json.loads(captured.out.strip())
    assert result["strict_output"] is True
    assert result["strict_output_source"] == "default"
    assert result["use_kb_source"] == "env"
    assert result["assistant_id"] == "assistant-id"
    assert result["assistant_id_source"] == "env"
    assert result["assistant_env"] == "OBNEXT_ASSISTANT_ID"
    assert result["assistant_env_source"] == "env"


def test_assistant_missing_reports_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("vision-assistant-env", raising=False)
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(vac, "_load_env_and_sanitize", lambda: None)
    monkeypatch.setattr(
        "semantic.vision_provision._load_vision_schema",
        lambda: {"type": "object", "properties": {}},
    )
    stub_settings = SimpleNamespace(
        vision_settings=SimpleNamespace(strict_output=True, use_kb=False),
        vision_model="gpt-test",
        vision_assistant_env="vision-assistant-env",
        openai_settings=SimpleNamespace(timeout=1, max_retries=1, http2_enabled=False),
    )
    monkeypatch.setattr(vac, "PipelineSettings", SimpleNamespace(load=lambda root: stub_settings))

    def _openai_factory(**kwargs: Any) -> _DummyOpenAI:
        return _DummyOpenAI(**kwargs)

    monkeypatch.setattr("openai.OpenAI", _openai_factory)

    with pytest.raises(SystemExit) as excinfo:
        vac.main()
    assert excinfo.value.code == 0

    output = json.loads(capsys.readouterr().out.strip())
    assert output["assistant_id"] is None
    assert output["assistant_id_source"] == "missing"
    assert output["assistant_env"] == "missing"
    assert output["assistant_env_source"] == "missing"
