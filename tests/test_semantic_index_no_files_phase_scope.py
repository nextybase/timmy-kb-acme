# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_index_no_files_phase_scope.py
import logging
from pathlib import Path

import semantic.api as api
from tests.support.contexts import TestClientCtx


class _DummyEmb:
    def embed_texts(self, texts, *, model=None):  # type: ignore[no-untyped-def]
        # Non verrà chiamato nel branch "no files", ma lo teniamo per sicurezza.
        return [[0.0, 0.0]]


def _ctx(base: Path, book: Path) -> TestClientCtx:
    return TestClientCtx(
        slug="dummy",
        base_dir=base,
        repo_root_dir=base,
        raw_dir=base / "raw",
        md_dir=book,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )


def test_index_markdown_no_files_emits_phase_and_artifacts_zero(tmp_path, caplog):
    base = tmp_path / "output" / "timmy-kb-dummy"
    book = base / "book"
    book.mkdir(parents=True, exist_ok=True)

    # Nessun file .md di contenuto (README/SUMMARY esclusi): branch "no files"
    (book / "README.md").write_text("# Readme\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")

    ctx = _ctx(base, book)

    caplog.set_level(logging.INFO)
    ret = api.index_markdown_to_db(
        ctx,
        logging.getLogger("test"),
        slug="dummy",
        scope="book",
        embeddings_client=_DummyEmb(),
        db_path=tmp_path / "db.sqlite",
    )
    assert ret == 0

    # Verifica eventi chiave di telemetria
    msgs = [r.getMessage() for r in caplog.records]
    assert "semantic.index.no_files" in msgs, "manca evento no_files"
    assert "semantic.index.done" in msgs, "manca evento di completamento fase"
    # Il phase_scope deve emettere start/completed anche in ramo 'no files'
    assert "phase_started" in msgs, "manca phase_started"
    assert "phase_completed" in msgs, "manca phase_completed"
