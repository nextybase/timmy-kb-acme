#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# tools/migrate_yaml_to_db.py
"""
Migra un file `tags_reviewed.yaml` verso il database SQLite `tags.db` adiacente.

Uso:
  python -m tools.migrate_yaml_to_db --yaml path/to/tags_reviewed.yaml
  python -m tools.migrate_yaml_to_db --slug acme --base-root output

Requisiti:
  - PyYAML installato (presente nel progetto)
  - Nessuna dipendenza extra (usa sqlite3 stdlib)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

from storage.tags_store import derive_db_path_from_yaml_path, save_tags_reviewed


def _load_yaml(path: Path) -> Dict[str, Any]:
    # Usa utility centrale per path-safety e SafeLoader
    try:
        from pipeline.yaml_utils import yaml_read

        return yaml_read(path.parent, path) or {}
    except Exception as e:
        raise SystemExit(f"Errore lettura YAML {path}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrazione tags_reviewed.yaml -> SQLite tags.db")
    ap.add_argument("--yaml", dest="yaml_path", help="Percorso a tags_reviewed.yaml")
    ap.add_argument("--slug", dest="slug", help="Slug cliente (usa base_root/output)")
    ap.add_argument("--base-root", dest="base_root", default="output", help="Root output (default: output)")
    args = ap.parse_args()

    yaml_path: Path
    if args.yaml_path:
        yaml_path = Path(args.yaml_path).expanduser().resolve()
    elif args.slug:
        yaml_path = (
            Path(args.base_root).expanduser().resolve() / f"timmy-kb-{args.slug}" / "semantic" / "tags_reviewed.yaml"
        )
    else:
        raise SystemExit("Specifica --yaml o --slug.")

    if not yaml_path.exists():
        raise SystemExit(f"File YAML non trovato: {yaml_path}")

    data = _load_yaml(yaml_path)
    db_path = derive_db_path_from_yaml_path(yaml_path)
    save_tags_reviewed(db_path, data)
    print(db_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
