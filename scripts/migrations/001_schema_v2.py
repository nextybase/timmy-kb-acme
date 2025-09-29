#!/usr/bin/env python3
# scripts/migrations/001_schema_v2.py
from __future__ import annotations

import argparse
from pathlib import Path

from storage.tags_store import ensure_schema_v2


def main() -> int:
    ap = argparse.ArgumentParser(description="Initialize/ensure SQLite schema v2 for tags DB")
    ap.add_argument("--db", dest="db_path", required=True, help="Path to tags.db")
    args = ap.parse_args()

    db_path = Path(args.db_path).expanduser().resolve()
    ensure_schema_v2(str(db_path))
    print(f"Schema v2 pronto: {db_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
