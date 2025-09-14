# tests/test_unit_emit_tags_csv.py
import csv
import logging
from pathlib import Path

from src.semantic.tags_extractor import emit_tags_csv as _emit_tags_csv


def test_emit_tags_csv_generates_posix_paths_and_header(tmp_path: Path):
    raw = tmp_path / "raw"
    sem = tmp_path / "semantic"
    raw.mkdir()
    sem.mkdir()
    # struttura annidata con nomi realistici
    nested = raw / "HR" / "Policies"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "Welcome Packet 2024.pdf").write_bytes(b"%PDF-1.4\n")
    (raw / "Security-Guide_v2.pdf").write_bytes(b"%PDF-1.4\n")

    csv_path = sem / "tags_raw.csv"
    # Passa un logger reale per soddisfare la signature (logging.Logger)
    written = _emit_tags_csv(raw, csv_path, logging.getLogger("test"))
    assert written == 2
    assert csv_path.exists()

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Header atteso
    assert reader.fieldnames == [
        "relative_path",
        "suggested_tags",
        "entities",
        "keyphrases",
        "score",
        "sources",
    ]

    rel_paths = {r["relative_path"] for r in rows}
    # Deve usare separatori POSIX e prefisso "raw/"
    assert "raw/HR/Policies/Welcome Packet 2024.pdf" in rel_paths
    assert "raw/Security-Guide_v2.pdf" in rel_paths
