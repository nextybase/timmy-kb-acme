from __future__ import annotations

import importlib
import os
from typing import Any


class _StubEmb:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial stub
        self.args = args
        self.kwargs = kwargs

    def embed_texts(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:  # noqa: D401
        return [[0.0] for _ in texts]


def test_coder_embeddings_fallback_from_codex_sets_openai_key_and_logs(monkeypatch, caplog):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "codex-secret")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    # Sostituiamo l'embedder per evitare dipendenze dall'SDK
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # Fallback applicato all'ambiente
    assert os.getenv("OPENAI_API_KEY") == "codex-secret"
    # Log di sorgente fallback presente
    assert any("embeddings.api_key.source=codex_fallback" in rec.message for rec in caplog.records)


def test_coder_embeddings_no_fallback_when_openai_key_present(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "codex-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "primary-secret")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # La chiave primaria resta invariata
    assert os.getenv("OPENAI_API_KEY") == "primary-secret"
    # Nessun log di fallback
    assert not any("embeddings.api_key.source=codex_fallback" in rec.message for rec in caplog.records)


def test_coder_embeddings_only_openai_key_also_works(monkeypatch, caplog):
    # Solo OPENAI_API_KEY presente: nessun fallback, ma client deve inizializzarsi
    monkeypatch.delenv("OPENAI_API_KEY_CODEX", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "primary-secret")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # Nessun log di fallback, usa la primaria
    assert not any("embeddings.api_key.source=codex_fallback" in rec.message for rec in caplog.records)
