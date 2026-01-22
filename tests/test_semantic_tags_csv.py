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
        raw_dir: Path
        book_dir: Path
        slug: str

    c = C()
    c.base_dir = base_dir
    c.repo_root_dir = base_dir
    c.raw_dir = base_dir / "raw"
    c.book_dir = base_dir / "book"
    c.slug = "dummy"
    return c


def test_build_tags_csv_from_raw(tmp_path):
    from semantic.api import build_tags_csv

    base = tmp_path / "output" / "timmy-kb-dummy"
    raw = base / "raw"
    book = base / "book"
    sem = base / "semantic"
    logs_dir = base / "logs"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("{}", encoding="utf-8")
    book.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (sem / "semantic_mapping.yaml").write_text("semantic_tagger: {}\n", encoding="utf-8")
    tags_db = sem / "tags.db"
    _ensure_tags_schema_v2(str(tags_db))
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (raw / "HR" / "Policies").mkdir(parents=True, exist_ok=True)
    (raw / "HR" / "Policies" / "Welcome Packet.pdf").write_bytes(b"%PDF-1.4\n")
    (raw / "Security-Guide_v2.pdf").write_bytes(b"%PDF-1.4\n")

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
        assert "raw/HR/Policies/Welcome Packet.pdf" in rels
        assert "raw/Security-Guide_v2.pdf" in rels
