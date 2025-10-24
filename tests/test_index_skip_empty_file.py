from __future__ import annotations

import logging
from pathlib import Path

import pytest

import semantic.api as sapi
from pipeline.logging_utils import get_structured_logger


class _Emb:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        # Un vettore per ciascun testo non-vuoto
        return [[1.0, 0.0] for _ in texts]


def test_index_logs_skip_empty_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    book = base / "book"
    db_path = base / "kb.sqlite"
    book.mkdir(parents=True, exist_ok=True)

    # Un file vuoto e uno non vuoto
    (book / "empty.md").write_text("   \n\t", encoding="utf-8")
    (book / "ok.md").write_text("# Title\nBody", encoding="utf-8")

    # Context minimo
    ctx = type("C", (), dict(base_dir=base, md_dir=book, slug="dummy"))()
    logger = get_structured_logger("tests.index.skip_empty", context=ctx)

    caplog.set_level(logging.INFO, logger="tests.index.skip_empty")

    inserted = sapi.index_markdown_to_db(
        ctx, logger, slug="dummy", scope="book", embeddings_client=_Emb(), db_path=db_path
    )
    # Potrebbe essere >=1 a seconda della logica di chunking; basta che indicizzi il file non-vuoto
    assert inserted >= 1

    # Deve comparire l’evento per-file sul markdown vuoto
    recs = [r for r in caplog.records if getattr(r, "event", r.getMessage()) == "semantic.index.skip_empty_file"]
    assert recs, "Evento semantic.index.skip_empty_file non trovato"
    assert any("empty.md" in str(getattr(r, "file_path", "")) for r in recs)
