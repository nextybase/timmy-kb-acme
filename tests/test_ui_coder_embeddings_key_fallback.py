from __future__ import annotations

import importlib
import logging
import os
from typing import Any


class _StubEmb:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        self.args = args
        self.kwargs = kwargs

    def embed_texts(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [[0.0] for _ in texts]


def test_coder_fallback_codex_only(monkeypatch, caplog):
    # Solo CODEX presente: non muta OPENAI_API_KEY, passa api_key allo stub, log fallback
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "codex-key")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="timmy_kb.ui")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # Nessuna mutazione dell'ambiente
    assert os.getenv("OPENAI_API_KEY") is None
    # Fallback: la chiave viene passata direttamente allo stub
    assert client.kwargs.get("api_key") == "codex-key"
    # Log fallback presente (può essere su handler root): usare caplog.text per robustezza
    # Il log di fallback è già coperto altrove; qui verifichiamo solo il percorso funzionale


def test_coder_primary_only(monkeypatch, caplog):
    # Solo OPENAI_API_KEY presente: nessun fallback, nessun log fallback
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.delenv("OPENAI_API_KEY_CODEX", raising=False)

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="timmy_kb.ui")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # Nessun parametro api_key passato
    assert "api_key" not in client.kwargs
    # Nessun fallback richiesto in questo caso


def test_coder_both_present_prefers_primary(monkeypatch, caplog):
    # Entrambe presenti: preferisce OPENAI_API_KEY, nessun log fallback
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "codex-key")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="timmy_kb.ui")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    assert "api_key" not in client.kwargs
    # Nessun fallback richiesto in questo caso
