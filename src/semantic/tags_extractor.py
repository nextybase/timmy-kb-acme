# -*- coding: utf-8 -*-
from __future__ import annotations
import csv
from pathlib import Path
from typing import List

from pipeline.path_utils import (
    is_safe_subpath,
    normalize_path,
    sanitize_filename,
    sorted_paths,
)

def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger) -> int:
    """Copia PDF da sorgente locale in raw/, con path-safety e idempotenza semplice."""
    src_dir = normalize_path(src_dir)
    raw_dir = normalize_path(raw_dir)

    if not src_dir.is_dir():
        raise FileNotFoundError(f"Percorso locale non valido: {src_dir}")

    count = 0
    pdfs: List[Path] = sorted_paths(src_dir.rglob("*.pdf"), base=src_dir)

    import shutil
    for src in pdfs:
        try:
            rel = src.relative_to(src_dir)
        except Exception:
            rel = Path(sanitize_filename(src.name))

        rel_sanitized = Path(*[sanitize_filename(p) for p in rel.parts])
        dst = raw_dir / rel_sanitized

        if not is_safe_subpath(dst, raw_dir):
            logger.warning("Skip per path non sicuro", extra={"file_path": str(dst)})
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                logger.debug("Skip copia (stessa dimensione)", extra={"file_path": str(dst)})
            else:
                shutil.copy2(src, dst)
                logger.info("PDF copiato", extra={"file_path": str(dst)})
                count += 1
        except Exception as e:
            logger.warning("Copia fallita", extra={"file_path": str(dst), "error": str(e)})

    return count


def emit_tags_csv(raw_dir: Path, csv_path: Path, logger) -> int:
    """
    Heuristica conservativa: per ogni PDF propone keyword grezze
    da nomi cartelle e filename. HiTL arricchirà in seguito.
    """
    rows: List[List[str]] = []
    for pdf in sorted_paths(raw_dir.rglob("*.pdf"), base=raw_dir):
        try:
            rel = pdf.relative_to(raw_dir).as_posix()
        except Exception:
            rel = pdf.name
        parts = [p for p in Path(rel).parts if p]
        base_no_ext = Path(parts[-1]).stem if parts else Path(rel).stem
        candidates = {p.lower() for p in parts[:-1]}
        candidates.update(tok for tok in base_no_ext.replace("_", " ").replace("-", " ").split() if tok)
        rows.append([rel, ", ".join(sorted(candidates))])

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["relative_path", "suggested_tags"])
        w.writerows(rows)

    logger.info("Tag grezzi generati", extra={"file_path": str(csv_path), "count": len(rows)})
    return len(rows)
