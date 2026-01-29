# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path

import storage.kb_db as kb


def test_insert_chunks_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "kb.sqlite"
    kb.init_db(db)

    project = "p"
    scope = "s"
    path = str(tmp_path / "a.md")
    version = "v1"
    meta = {"source": "test"}
    chunks = ["uno", "due", "tre"]
    embeddings = [[1.0, 0.0]] * 3

    first = kb.insert_chunks(project, scope, path, version, meta, chunks, embeddings, db_path=db)
    second = kb.insert_chunks(project, scope, path, version, meta, chunks, embeddings, db_path=db)

    # La seconda insert non deve introdurre duplicati
    items = list(kb.fetch_candidates(project, scope, limit=1000, db_path=db))

    assert first == 3
    # second potrebbe essere 0 (IGNORE) a seconda del driver; tollera 0
    assert second in (0, 3) or second <= 3
    assert len(items) == 3
