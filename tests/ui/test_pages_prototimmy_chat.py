# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence

import pytest

from ui.pages import prototimmy_chat as page


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.json_payloads: list[dict[str, object]] = []
        self.success_calls: list[str] = []
        self.error_calls: list[str] = []
        self.write_calls: list[str] = []
        self.chat_roles: list[str] = []

    def button(self, label: str, *args: object, **kwargs: object) -> bool:
        return label == "Esegui smoke test"

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
        return ""

    def caption(self, *args: object, **kwargs: object) -> None:
        return None


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
