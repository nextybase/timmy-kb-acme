# tests/test_semantic_tags_csv.py
# cspell:ignore rels
import csv
import logging
from pathlib import Path
from typing import Any, cast


def _ctx(base_dir: Path):
    class C:
        # Attributi dichiarati per soddisfare Pylance
        base_dir: Path
        raw_dir: Path
        md_dir: Path
        slug: str

    c = C()
    c.base_dir = base_dir
    c.raw_dir = base_dir / "raw"
    c.md_dir = base_dir / "book"
    c.slug = "dummy"
    return c


def test_build_tags_csv_from_raw(tmp_path):
    from semantic.api import build_tags_csv

    base = tmp_path / "output" / "timmy-kb-dummy"
    raw = base / "raw"
    sem = base / "semantic"
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
