# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import semantic.api as sapi
from pipeline.logging_utils import get_structured_logger
from tests._helpers.workspace_paths import local_workspace_dir


class _Emb:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        # Un vettore per ciascun testo non-vuoto
        return [[1.0, 0.0] for _ in texts]


def _ensure_minimal_workspace(base: Path) -> None:
    config_dir = base / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    for child in ("raw", "normalized", "book", "semantic", "logs"):
        (base / child).mkdir(parents=True, exist_ok=True)
    book_dir = base / "book"
    (book_dir / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")


def test_index_logs_skip_empty_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = local_workspace_dir(tmp_path / "output", "dummy")
    _ensure_minimal_workspace(base)
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)

    # Un file con solo frontmatter (body vuoto) e uno non vuoto
    (book / "empty.md").write_text("---\ntitle: Empty\n---\n", encoding="utf-8")
    (book / "ok.md").write_text("---\ntitle: OK\n---\n# Title\nBody", encoding="utf-8")

    # Context minimo
    ctx = type("C", (), dict(base_dir=base, book_dir=book, repo_root_dir=base, slug="dummy"))()
    logger = get_structured_logger("tests.index.skip_empty", context=ctx)

    caplog.set_level(logging.INFO, logger="tests.index.skip_empty")

    inserted = sapi.index_markdown_to_db(ctx, logger, slug="dummy", scope="book", embeddings_client=_Emb())
    # Potrebbe essere >=1 a seconda della logica di chunking; basta che indicizzi il file non-vuoto
    assert inserted >= 1

    # Deve comparire l'evento per-file sul markdown vuoto
    recs = [r for r in caplog.records if getattr(r, "event", r.getMessage()) == "semantic.index.skip_empty_file"]
    assert recs, "Evento semantic.index.skip_empty_file non trovato"
    assert any("empty.md" in str(getattr(r, "file_path", "")) for r in recs)
