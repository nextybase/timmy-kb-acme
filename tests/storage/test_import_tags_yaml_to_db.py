# SPDX-License-Identifier: GPL-3.0-only
# tests/storage/test_import_tags_yaml_to_db.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from storage.tags_store import (
    derive_db_path_from_yaml_path,
    ensure_schema_v2,
    get_conn,
    get_term_by_canonical,
    import_tags_yaml_to_db,
    list_folders,
    list_term_aliases,
)

YAML_MINIMAL = """\
version: "2"
reviewed_at: "2025-01-01T00:00:00"
keep_only_listed: false
tags:
  - canonical: "brand identity"
    aliases: ["identita di marca", "branding"]
    folders:
      - "raw/marketing"
      - { path: "book/brochure", weight: 2.0, status: "keep" }
  - canonical: "crm"
    folders: ["marketing/crm"]  # no prefix -> raw/marketing/crm
"""


def _readall(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    cur = conn.execute(sql)
    return cur.fetchall()


def test_import_yaml_to_db_idempotent(tmp_path: Path):
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    yaml_path.write_text(YAML_MINIMAL, encoding="utf-8")

    db_path = derive_db_path_from_yaml_path(yaml_path)
    ensure_schema_v2(db_path)

    # 1) primo import
    stats1 = import_tags_yaml_to_db(yaml_path)
    assert stats1["terms"] == 2
    assert stats1["folders"] >= 2
    assert stats1["links"] >= 3
    assert stats1["skipped"] == 0

    # 2) re-import idempotente (nessun duplicato)
    stats2 = import_tags_yaml_to_db(yaml_path)
    # conteggi cumulativi devono restare identici (idempotenza)
    assert stats2 == stats1
    with get_conn(db_path) as conn:
        terms = _readall(conn, "SELECT canonical, COUNT(*) FROM terms GROUP BY canonical")
        assert all(cnt == 1 for _, cnt in terms)

        # alias unici
        tid = get_term_by_canonical(conn, "brand identity")["id"]
        aliases = list_term_aliases(conn, tid)
        assert set(a.lower() for a in aliases) == {"identita di marca", "branding"}

        # folders uniche
        folders = list_folders(conn)
        paths = [f["path"] for f in folders]
        # normalizzazione: marketing/crm -> raw/marketing/crm
        assert "raw/marketing/crm" in paths

        # folder_terms univoci
        ft = _readall(conn, "SELECT folder_id, term_id, COUNT(*) FROM folder_terms GROUP BY 1,2")
        assert all(cnt == 1 for *_, cnt in ft)


def test_import_yaml_rejects_unsafe_paths(tmp_path: Path):
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    bad_yaml = semantic_dir / "tags_reviewed.yaml"
    bad_yaml.write_text(
        """\
version: "2"
tags:
  - canonical: "alpha"
    folders: ["../outside"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        import_tags_yaml_to_db(bad_yaml)


def test_import_yaml_without_pyyaml_fallback(monkeypatch, tmp_path: Path):
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    yaml_path.write_text(YAML_MINIMAL, encoding="utf-8")

    import storage.tags_store as ts

    old_yaml = ts.yaml
    try:
        ts.yaml = None  # simula PyYAML mancante
        stats = import_tags_yaml_to_db(yaml_path)
        assert stats["terms"] == 2
        assert stats["skipped"] == 0
    finally:
        ts.yaml = old_yaml
