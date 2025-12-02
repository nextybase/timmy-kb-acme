# SPDX-License-Identifier: GPL-3.0-only
# tests/test_kb_db_path_safety.py
from pathlib import Path

from kb_db import insert_chunks


def test_db_default_under_data(tmp_path: Path, monkeypatch):
    # Isola il working dir: il DB predefinito (data/kb.sqlite) verrà creato sotto tmp_path
    monkeypatch.chdir(tmp_path)

    inserted = insert_chunks(
        slug="obs",
        scope="s",
        path="p",
        version="v",
        meta_dict={},
        chunks=["c1"],
        embeddings=[[1.0]],
        db_path=None,  # usa data/kb.sqlite relativo al cwd (qui: tmp_path)
    )
    assert inserted == 1
