import timmy_kb_coder as coder


class _UI:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warning(self, text: str) -> None:
        self.messages.append(text)


def test_rag_warning_mentions_both_keys(monkeypatch):
    ui = _UI()
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "")
    monkeypatch.setattr(coder, "st", ui, raising=False)

    client = coder._emb_client_or_none(use_rag=True)

    assert client is None
    assert ui.messages
    message = ui.messages[0]
    assert "OPENAI_API_KEY" in message
    assert "OPENAI_API_KEY_CODEX" in message
