# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from storage.tags_store import ensure_schema_v2


def test_ensure_schema_v2_fails_on_existing_db_without_meta(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()

    with pytest.raises(ConfigError) as excinfo:
        ensure_schema_v2(str(db_path))
    assert "legacy tags.db detected" in str(excinfo.value)


def test_ensure_schema_v2_fails_on_existing_db_with_wrong_version(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic" / "tags.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            (
                "CREATE TABLE IF NOT EXISTS meta("
                "id INTEGER PRIMARY KEY, "
                "version TEXT, "
                "reviewed_at TEXT, "
                "keep_only_listed INTEGER"
                ")"
            )
        )
        conn.execute("INSERT INTO meta(id, version, reviewed_at, keep_only_listed) VALUES(1, '1', 'now', 0)")
        conn.commit()

    with pytest.raises(ConfigError) as excinfo:
        ensure_schema_v2(str(db_path))
    assert "legacy tags.db detected" in str(excinfo.value)
