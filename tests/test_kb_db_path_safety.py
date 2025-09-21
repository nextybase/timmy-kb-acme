from __future__ import annotations

from pathlib import Path

import pytest

from kb_db import fetch_candidates, insert_chunks


def test_db_default_under_data(tmp_path, monkeypatch):
    # Isola il CWD: il DB predefinito (data/kb.sqlite) vive sotto tmp_path
    monkeypatch.chdir(tmp_path)
    # Inserisce una riga usando il DB predefinito (data/kb.sqlite)
    inserted = insert_chunks(
        project_slug="obs",
        scope="s",
        path="p",
        version="v",
        meta_dict={},
        chunks=["c1"],
        embeddings=[[1.0]],
        db_path=None,
    )
    assert inserted == 1
    # Recupera almeno una riga
    cands = list(fetch_candidates("obs", "s", limit=1, db_path=None))
    assert cands and cands[0]["content"] == "c1"


def test_db_relative_outside_data_raises(tmp_path, monkeypatch):
    # Isola il CWD per evitare interferenze con il repo
    monkeypatch.chdir(tmp_path)
    # Un path relativo con traversal non deve essere accettato (ancorato a data/)
    bad = Path("..") / "evil.sqlite"
    with pytest.raises(Exception):
        insert_chunks(
            project_slug="x",
            scope="y",
            path="p",
            version="v",
            meta_dict={},
            chunks=["c"],
            embeddings=[[1.0]],
            db_path=bad,
        )
