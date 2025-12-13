# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence

import pytest

from ai.codex_runner import StructuredResult
from ui.pages import prototimmy_chat as page


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.json_payloads: list[dict[str, object]] = []
        self.success_calls: list[str] = []
        self.error_calls: list[str] = []
        self.write_calls: list[str] = []
        self.chat_roles: list[str] = []
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.button_returns: dict[str, bool] = {}

    def button(self, label: str, *args: object, **kwargs: object) -> bool:
        return self.button_returns.get(label, label == "Esegui smoke test")

    def json(self, payload: dict[str, object]) -> None:
        self.json_payloads.append(payload)

    def success(self, message: str) -> None:
        self.success_calls.append(message)

    def error(self, message: str) -> None:
        self.error_calls.append(message)

    def write(self, value: object) -> None:
        self.write_calls.append(str(value))

    def markdown(self, text: str) -> None:
        self.write_calls.append(text)

    def chat_message(self, role: str) -> object:
        class _Context:
            def __enter__(inner_self) -> object:
                self.chat_roles.append(role)
                return inner_self

            def __exit__(inner_self, exc_type, exc_value, traceback) -> bool:
                return False

        return _Context()

    def chat_input(self, *args: object, **kwargs: object) -> str | None:
        return None

    def text_area(self, *args: object, **kwargs: object) -> str:
        key = kwargs.get("key")
        value = kwargs.get("value", "")
        if key:
            if key not in self.session_state:
                self.session_state[key] = value or ""
            return str(self.session_state[key])
        return str(value)

    def caption(self, *args: object, **kwargs: object) -> None:
        return None

    def info(self, message: str) -> None:
        self.info_calls.append(message)

    def warning(self, message: str) -> None:
        self.warning_calls.append(message)

    def code(self, value: object, language: str | None = None) -> None:
        self.write_calls.append(str(value))

    def subheader(self, text: str) -> None:
        self.write_calls.append(text)


@pytest.fixture()
def streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> _StreamlitStub:
    stub = _StreamlitStub()
    monkeypatch.setattr(page, "st", stub)
    return stub


def test_smoke_button_triggers_check(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    monkeypatch.setattr(page, "render_chrome_then_require", lambda **_: None)

    invoked: dict[str, int] = {"count": 0}

    def fake_check(**kwargs: object) -> dict[str, object]:
        invoked["count"] += 1
        return {"ok": True, "steps": []}

    monkeypatch.setattr(page, "run_prototimmy_dummy_check", fake_check)
    monkeypatch.setattr(page, "_load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(page, "resolve_prototimmy_config", lambda *_: SimpleNamespace(model="test-model"))
    monkeypatch.setattr(
        page,
        "run_text_model",
        lambda *args, **kwargs: SimpleNamespace(text="hello"),
    )

    page.main()

    assert invoked["count"] == 1
    assert streamlit_stub.json_payloads
    assert streamlit_stub.json_payloads[-1] == {"ok": True, "steps": []}
    assert streamlit_stub.success_calls


def test_invoke_prototimmy_json_filters_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    history = [
        dict(page._SYSTEM_MESSAGE),
        {"role": "user", "content": "Ciao"},
        {"role": "assistant", "content": "Ok"},
        {"role": "user", "content": "Secondo messaggio"},
    ]

    captured: dict[str, list] = {"messages": []}

    def fake_run_json_model(*, model: str, messages: Sequence[dict[str, object]], **kwargs: object) -> SimpleNamespace:
        captured["messages"] = list(messages)
        return SimpleNamespace(text="ignored", data={"reply_to_user": "ok", "message_for_ocp": "delega"})

    monkeypatch.setattr(page, "_load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(page, "resolve_prototimmy_config", lambda *_: SimpleNamespace(model="m"))
    monkeypatch.setattr(page, "run_json_model", fake_run_json_model)

    response, ocp_request = page._invoke_prototimmy_json(history, "Secondo messaggio")

    assert response.startswith("ok")
    assert ocp_request == "delega"
    assert len(captured["messages"]) == 2
    assert captured["messages"][0]["role"] == "system"
    assert "UTENTE: Secondo messaggio" in captured["messages"][1]["content"]
    assert "PROTOTIMMY" in captured["messages"][1]["content"]


def _setup_codex_validation(
    monkeypatch: pytest.MonkeyPatch,
    streamlit_stub: _StreamlitStub,
    response_data: dict[str, object],
) -> None:
    monkeypatch.setattr(page, "render_chrome_then_require", lambda **_: None)
    monkeypatch.setattr(page, "_load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(page, "resolve_ocp_executor_config", lambda *_: SimpleNamespace(model="ocp-model"))
    streamlit_stub.session_state[page._CODEX_OUTPUT_KEY] = "output"
    streamlit_stub.session_state[page._CODEX_PROMPT_KEY] = "Prompt iniziale"
    streamlit_stub.button_returns["Valida output Codex"] = True

    def fake_run_json_model(*, model: str, messages: Sequence[dict[str, object]], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(data=response_data)

    monkeypatch.setattr(page, "run_json_model", fake_run_json_model)


def _setup_codex_cli_run(
    monkeypatch: pytest.MonkeyPatch,
    streamlit_stub: _StreamlitStub,
    result: StructuredResult,
) -> None:
    monkeypatch.setattr(page, "render_chrome_then_require", lambda **_: None)
    monkeypatch.setattr(page, "_load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(page, "resolve_ocp_executor_config", lambda *_: SimpleNamespace(model="ocp-model"))
    monkeypatch.setattr(page, "run_codex_cli", lambda *args, **kwargs: result)
    streamlit_stub.button_returns["Esegui Codex CLI (locale)"] = True
    streamlit_stub.button_returns["Valida output Codex"] = False
    streamlit_stub.button_returns["Esegui smoke test"] = False


def test_codex_hitl_unlock_button(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    streamlit_stub.session_state[page._CODEX_HITL_KEY] = True
    streamlit_stub.session_state[page._CODEX_PROMPT_KEY] = "Prompt corrente"
    streamlit_stub.session_state[page._CODEX_OUTPUT_KEY] = "Output corrente"
    streamlit_stub.button_returns["Valida output Codex"] = False
    streamlit_stub.button_returns["Esegui Codex CLI (locale)"] = False
    streamlit_stub.button_returns["Sblocca HITL (supervisore)"] = True
    streamlit_stub.button_returns["Esegui smoke test"] = False
    monkeypatch.setattr(page, "render_chrome_then_require", lambda **_: None)

    page._render_codex_section()

    assert not streamlit_stub.session_state.get(page._CODEX_HITL_KEY)
    assert streamlit_stub.session_state[page._CODEX_PROMPT_KEY] == "Prompt corrente"
    assert streamlit_stub.session_state[page._CODEX_OUTPUT_KEY] == "Output corrente"


def test_codex_validation_success(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    response_data = {
        "ok": True,
        "issues": [],
        "next_prompt_for_codex": "Nuovo prompt",
        "stop_code": "",
    }
    _setup_codex_validation(monkeypatch, streamlit_stub, response_data)

    page.main()

    assert streamlit_stub.success_calls
    assert any("Next prompt" in msg for msg in streamlit_stub.info_calls)
    assert streamlit_stub.session_state[page._CODEX_PROMPT_KEY] == "Nuovo prompt"


def test_codex_validation_failure(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    response_data = {
        "ok": False,
        "issues": ["errore 1"],
        "next_prompt_for_codex": "",
        "stop_code": "",
    }
    _setup_codex_validation(monkeypatch, streamlit_stub, response_data)

    page.main()

    assert streamlit_stub.error_calls
    assert any("errore 1" in msg for msg in streamlit_stub.error_calls)


def test_codex_validation_triggers_hitl(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    response_data = {
        "ok": True,
        "issues": [],
        "next_prompt_for_codex": "",
        "stop_code": "HITL_REQUIRED",
    }
    _setup_codex_validation(monkeypatch, streamlit_stub, response_data)

    page.main()

    assert streamlit_stub.warning_calls
    assert streamlit_stub.session_state.get(page._CODEX_HITL_KEY)


def test_codex_cli_button_success(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    result = StructuredResult(
        ok=True,
        exit_code=0,
        stdout="output-ok",
        stderr="",
        duration_ms=10,
        error=None,
    )
    _setup_codex_cli_run(monkeypatch, streamlit_stub, result)

    page.main()

    assert streamlit_stub.session_state[page._CODEX_OUTPUT_KEY] == "output-ok"
    assert streamlit_stub.success_calls


def test_codex_cli_button_failure(monkeypatch: pytest.MonkeyPatch, streamlit_stub: _StreamlitStub) -> None:
    result = StructuredResult(
        ok=False,
        exit_code=2,
        stdout="",
        stderr="warn",
        duration_ms=5,
        error="boom",
    )
    _setup_codex_cli_run(monkeypatch, streamlit_stub, result)

    page.main()

    assert streamlit_stub.error_calls
    assert any("exit 2" in msg for msg in streamlit_stub.error_calls)
