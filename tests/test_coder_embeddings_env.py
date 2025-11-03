# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import types
from typing import Any

try:
    import streamlit as st
except ImportError:
    st = types.SimpleNamespace(
        error=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        success=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        set_page_config=lambda *args, **kwargs: None,
        session_state={},
    )
else:
    for _name in (
        "error",
        "info",
        "success",
        "warning",
        "set_page_config",
    ):
        if not hasattr(st, _name):
            setattr(st, _name, lambda *args, **kwargs: None)
    if not hasattr(st, "session_state"):
        st.session_state = {}


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
    # Fallback soft: non muta l'ambiente, passa la chiave direttamente al client
    assert getattr(client, "kwargs", {}).get("api_key") == "codex-secret"
    # Log di sorgente fallback presente (logging strutturato: event + extra)
    assert any(
        rec.message == "embeddings.api_key" and getattr(rec, "source", None) == "codex_fallback"
        for rec in caplog.records
    )


def test_coder_embeddings_no_fallback_when_openai_key_present(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY_CODEX", "codex-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "primary-secret")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _StubEmb, raising=True)

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert isinstance(client, _StubEmb)
    # La chiave primaria resta invariata (nessun parametro passato al client)
    assert "api_key" not in getattr(client, "kwargs", {})
    # Nessun log di fallback
    assert not any(
        rec.message == "embeddings.api_key" and getattr(rec, "source", None) == "codex_fallback"
        for rec in caplog.records
    )


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
    # Nessun parametro api_key passato esplicitamente
    assert "api_key" not in getattr(client, "kwargs", {})
    # Nessun log di fallback, usa la primaria
    assert not any(
        rec.message == "embeddings.api_key" and getattr(rec, "source", None) == "codex_fallback"
        for rec in caplog.records
    )


def test_coder_embeddings_handles_missing_streamlit(monkeypatch, caplog):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_CODEX", raising=False)

    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    tkc.st = None

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert client is None
    assert any(rec.message == "coder.rag.disabled" for rec in caplog.records)
    assert any(getattr(rec, "event", None) == "coder.rag.disabled" for rec in caplog.records)


def test_coder_embeddings_logs_disabled_on_init_error(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-secret")

    import timmy_kb_coder as tkc

    importlib.reload(tkc)

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(tkc, "OpenAIEmbeddings", _raise, raising=True)

    caplog.set_level("INFO")
    client = tkc._emb_client_or_none(use_rag=True)

    assert client is None
    assert any(
        rec.message == "coder.rag.disabled" and getattr(rec, "reason", None) == "init_error" for rec in caplog.records
    )
