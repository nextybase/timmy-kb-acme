# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_tags_csv.py
# cspell:ignore rels
import csv
import logging
from pathlib import Path
from typing import Any, cast

from storage.tags_store import ensure_schema_v2 as _ensure_tags_schema_v2


def _ctx(base_dir: Path):
    class C:
        # Attributi dichiarati per soddisfare Pylance
        base_dir: Path
        repo_root_dir: Path
        normalized_dir: Path
        book_dir: Path
        slug: str

    c = C()
    c.base_dir = base_dir
    c.repo_root_dir = base_dir
    c.normalized_dir = base_dir / "normalized"
    c.book_dir = base_dir / "book"
    c.slug = "dummy"
    return c


def test_build_tags_csv_from_normalized(tmp_path):
    from semantic.api import build_tags_csv

    base = tmp_path / "output" / "timmy-kb-dummy"
    normalized = base / "normalized"
    book = base / "book"
    sem = base / "semantic"
    logs_dir = base / "logs"
    raw = base / "raw"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    book.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    (sem / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    tags_db = sem / "tags.db"
    _ensure_tags_schema_v2(str(tags_db))
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (normalized / "HR" / "Policies").mkdir(parents=True, exist_ok=True)
    (normalized / "HR" / "Policies" / "Welcome Packet.md").write_text("# Welcome\n", encoding="utf-8")
    (normalized / "Security-Guide_v2.md").write_text("# Security\n", encoding="utf-8")

    # cast(Any, …): bypass del nominal type (ClientContext) mantenendo invariata la logica
    csv_path = build_tags_csv(cast(Any, _ctx(base)), logging.getLogger("test"), slug="dummy")
    assert csv_path.exists()
    assert csv_path.parent == sem

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert reader.fieldnames == [
            "relative_path",
            "suggested_tags",
            "entities",
            "keyphrases",
            "score",
            "sources",
        ]
        rels = {r["relative_path"] for r in rows}
        assert "normalized/HR/Policies/Welcome Packet.md" in rels
        assert "normalized/Security-Guide_v2.md" in rels
