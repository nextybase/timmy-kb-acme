from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Tuple

from .store import import_csv as _import_csv, summarize_metrics as _summarize_metrics

__all__ = ["import_csv", "summarize_metrics"]


def import_csv(base_dir: Path, csv_path: Path) -> Dict[str, Any]:
    return _import_csv(base_dir, csv_path)


def summarize_metrics(base_dir: Path) -> List[Tuple[str, int]]:
    return _summarize_metrics(base_dir)
