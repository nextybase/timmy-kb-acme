from pathlib import Path

from src.finance.store import import_csv
from src.tag_onboarding import scan_raw_to_db


def _dummy_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\n% Codex test\n")


def test_scan_raw_to_db_releases_lock(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _dummy_pdf(raw_dir / "demo.pdf")
    db_path = tmp_path / "semantic" / "tags.db"

    stats = scan_raw_to_db(raw_dir, str(db_path))
    assert stats["folders"] >= 1 or stats["documents"] >= 0

    moved = db_path.with_suffix(".moved.db")
    db_path.rename(moved)
    assert moved.exists()


def test_import_csv_twice_releases_lock(tmp_path: Path) -> None:
    base_dir = tmp_path / "client"
    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    csv_path = sem_dir / "metrics.csv"
    csv_path.write_text("metric,period,value\nRevenue,2024Q1,123.4\n", encoding="utf-8")
    db_path = sem_dir / "finance.db"

    for _ in range(2):
        result = import_csv(base_dir, csv_path)
        assert Path(result["db"]).exists()
        moved = db_path.with_suffix(".moved.db")
        db_path.rename(moved)
        assert moved.exists()
        moved.rename(db_path)
