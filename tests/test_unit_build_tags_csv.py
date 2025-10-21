# tests/test_unit_build_tags_csv.py
import csv
import logging
from pathlib import Path
from types import SimpleNamespace

from timmykb.semantic.api import build_tags_csv


def test_build_tags_csv_generates_posix_paths_and_header(tmp_path: Path) -> None:
    slug = "dummy"
    base_root = tmp_path / "output"
    base_dir = base_root / f"timmy-kb-{slug}"
    raw = base_dir / "raw"
    sem = base_dir / "semantic"
    book = base_dir / "book"
    config_dir = base_dir / "config"

    raw.mkdir(parents=True, exist_ok=True)
    sem.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")
    (sem / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")

    nested = raw / "HR" / "Policies"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "Welcome Packet 2024.pdf").write_bytes(b"%PDF-1.4\n")
    (raw / "Security-Guide_v2.pdf").write_bytes(b"%PDF-1.4\n")

    context = SimpleNamespace(base_dir=base_dir, raw_dir=raw, md_dir=book)
    csv_path = build_tags_csv(context, logging.getLogger("test"), slug=slug)

    assert csv_path == sem / "tags_raw.csv"
    assert csv_path.exists()

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
    assert len(rows) == 2

    rel_paths = {r["relative_path"] for r in rows}
    assert "raw/HR/Policies/Welcome Packet 2024.pdf" in rel_paths
    assert "raw/Security-Guide_v2.pdf" in rel_paths
