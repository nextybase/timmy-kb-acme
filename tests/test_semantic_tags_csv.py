import csv
import logging
from pathlib import Path


def _ctx(base_dir: Path):
    class C:
        pass

    c = C()
    c.base_dir = base_dir
    c.raw_dir = base_dir / "raw"
    c.md_dir = base_dir / "book"
    c.slug = "x"
    return c


def test_build_tags_csv_from_raw(tmp_path):
    from semantic.api import build_tags_csv

    base = tmp_path / "output" / "timmy-kb-x"
    raw = base / "raw"
    sem = base / "semantic"
    (raw / "HR" / "Policies").mkdir(parents=True, exist_ok=True)
    (raw / "HR" / "Policies" / "Welcome Packet.pdf").write_bytes(b"%PDF-1.4\n")
    (raw / "Security-Guide_v2.pdf").write_bytes(b"%PDF-1.4\n")

    csv_path = build_tags_csv(_ctx(base), logging.getLogger("test"), slug="x")
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
