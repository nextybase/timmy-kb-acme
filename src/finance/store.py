from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from pipeline.path_utils import ensure_within

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metrics(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  unit TEXT,
  UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS observations(
  id INTEGER PRIMARY KEY,
  metric_id INTEGER NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
  period TEXT NOT NULL,
  value  REAL NOT NULL,
  currency TEXT,
  note TEXT,
  UNIQUE(metric_id, period)
);

-- Link opzionale: metrica ↔ termine canonico (nome canonical in tags.db)
CREATE TABLE IF NOT EXISTS metric_term_links(
  metric_id INTEGER NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
  canonical TEXT NOT NULL,
  UNIQUE(metric_id, canonical)
);
"""


def get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_metric(conn: sqlite3.Connection, name: str, unit: Optional[str]) -> int:
    name = (name or "").strip()
    unit_val = (unit or "").strip() or None
    if not name:
        raise ValueError("Metric name is empty")
    conn.execute(
        "INSERT INTO metrics(name, unit) VALUES(?, ?) "
        "ON CONFLICT(name) DO UPDATE SET unit=COALESCE(excluded.unit, unit)",
        (name, unit_val),
    )
    row = conn.execute("SELECT id FROM metrics WHERE name=?", (name,)).fetchone()
    return int(row[0])


def upsert_observation(
    conn: sqlite3.Connection,
    metric_id: int,
    period: str,
    value: float,
    currency: Optional[str],
    note: Optional[str],
) -> None:
    period = (period or "").strip()
    if not period:
        raise ValueError("Period is empty")
    conn.execute(
        (
            "INSERT INTO observations(metric_id, period, value, currency, note) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(metric_id, period) DO UPDATE SET "
            "value=excluded.value, currency=excluded.currency, note=excluded.note"
        ),
        (int(metric_id), period, float(value), (currency or None), (note or None)),
    )


def link_metric_to_canonical(conn: sqlite3.Connection, metric_id: int, canonical: str) -> None:
    canonical = (canonical or "").strip()
    if not canonical:
        return
    conn.execute(
        "INSERT OR IGNORE INTO metric_term_links(metric_id, canonical) VALUES(?, ?)",
        (int(metric_id), canonical),
    )


def summarize(conn: sqlite3.Connection) -> List[Tuple[str, int]]:
    cur = conn.execute(
        "SELECT m.name, COUNT(o.id) FROM metrics m "
        "LEFT JOIN observations o ON o.metric_id=m.id "
        "GROUP BY m.id, m.name ORDER BY m.name COLLATE NOCASE ASC"
    )
    return [(str(r[0]), int(r[1])) for r in cur.fetchall()]


def import_csv(base_dir: Path, csv_path: Path) -> Dict[str, Any]:
    """Importa CSV di metriche in semantic/finance.db

    CSV atteso: metric, period, value, [unit], [currency], [note], [canonical_term]
    """
    base_dir = Path(base_dir).resolve()
    csv_path = Path(csv_path).resolve()
    sem_dir = base_dir / "semantic"

    # Consenti lettura CSV solo sotto semantic/
    ensure_within(sem_dir, csv_path)

    db_path = sem_dir / "finance.db"
    conn = get_conn(db_path)
    ensure_schema(conn)

    created = 0
    updated = 0

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            metric = (row.get("metric") or "").strip()
            period = (row.get("period") or "").strip()
            value_s = (row.get("value") or "").strip()
            unit = (row.get("unit") or "").strip() or None
            currency = (row.get("currency") or "").strip() or None
            note = (row.get("note") or "").strip() or None
            canonical = (row.get("canonical_term") or "").strip()
            if not metric or not period or not value_s:
                continue
            try:
                val = float(value_s.replace(",", "."))
            except Exception:
                continue
            mid = upsert_metric(conn, metric, unit)
            # prova insert/update e conta
            before = conn.execute(
                "SELECT 1 FROM observations WHERE metric_id=? AND period=?",
                (mid, period),
            ).fetchone()
            upsert_observation(conn, mid, period, val, currency, note)
            after = conn.execute(
                "SELECT 1 FROM observations WHERE metric_id=? AND period=?",
                (mid, period),
            ).fetchone()
            if before is None and after is not None:
                created += 1
            else:
                updated += 1
            if canonical:
                link_metric_to_canonical(conn, mid, canonical)
    conn.commit()
    return {"db": str(db_path), "rows": created, "updated": updated}


def summarize_metrics(base_dir: Path) -> List[Tuple[str, int]]:
    sem_dir = Path(base_dir).resolve() / "semantic"
    db_path = sem_dir / "finance.db"
    conn = get_conn(db_path)
    ensure_schema(conn)
    return summarize(conn)


__all__ = [
    "import_csv",
    "summarize_metrics",
]
