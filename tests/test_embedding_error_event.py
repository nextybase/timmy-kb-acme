# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import semantic.api as sapi
from pipeline.logging_utils import get_structured_logger


class _BoomEmb:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")


def test_embedding_error_is_logged_and_raised(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    book = base / "book"
    db_path = base / "kb.sqlite"
    book.mkdir(parents=True, exist_ok=True)
    (book / "a.md").write_text("# A\nBody", encoding="utf-8")

    ctx = type("C", (), dict(base_dir=base, md_dir=book, slug="dummy"))()
    logger = get_structured_logger("tests.index.emb_error", context=ctx)

    caplog.set_level(logging.INFO, logger="tests.index.emb_error")

    with pytest.raises(RuntimeError):
        sapi.index_markdown_to_db(
            ctx, logger, slug="dummy", scope="book", embeddings_client=_BoomEmb(), db_path=db_path
        )

    # Deve essere presente l'evento strutturato con dettaglio dell'errore
    events = [r for r in caplog.records if getattr(r, "event", r.getMessage()) == "semantic.index.embedding_error"]
    assert events, "Evento semantic.index.embedding_error non trovato"
    last = events[-1]
    assert "boom" in str(getattr(last, "error", "")), "Dettaglio errore mancante"
    assert getattr(last, "count", None) in (1, "1"), "Conteggio testi non coerente"
