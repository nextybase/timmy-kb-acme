# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from pathlib import Path

from pipeline.exceptions import ConfigError  # ✅ per segnalare path traversal


def _ensure_within(base: Path, target: Path) -> None:
    """
    Garantisce che 'target' risieda sotto 'base' una volta risolti i path.
    Solleva ConfigError in caso contrario.
    """
    base_r = base.resolve()
    tgt_r = target.resolve()
    if not str(tgt_r).startswith(str(base_r)):
        raise ConfigError(f"Path traversal rilevato: {tgt_r} non è sotto {base_r}")


def write_tagging_readme(semantic_dir: Path, logger) -> Path:
    semantic_dir.mkdir(parents=True, exist_ok=True)
    out = semantic_dir / "README_TAGGING.md"
    _ensure_within(semantic_dir, out)  # ✅ guardia anti path traversal
    out.write_text(
        "# Tag Onboarding (HiTL) – Guida rapida\n\n"
        "1. Apri `tags_raw.csv` e valuta i suggerimenti.\n"
        "2. Compila `tags_reviewed.yaml` (keep/drop/merge).\n"
        "3. Quando pronto, crea/aggiorna `tags.yaml` con i tag canonici + sinonimi.\n",
        encoding="utf-8",
    )
    logger.info("README_TAGGING scritto", extra={"file_path": str(out)})
    return out


def write_tags_review_stub_from_csv(semantic_dir: Path, csv_path: Path, logger, top_n: int = 100) -> Path:
    rows = (csv_path.read_text(encoding="utf-8").splitlines())[1:]  # salta header
    suggested = []
    for r in rows[:top_n]:
        try:
            _, suggested_str = r.split(",", 1)
            first = (suggested_str or "").split(",")[0].strip()
            if first:
                suggested.append(first)
        except Exception:
            continue
    out = semantic_dir / "tags_reviewed.yaml"
    _ensure_within(semantic_dir, out)  # ✅ guardia anti path traversal
    lines = [
        "version: 1",
        f"reviewed_at: \"{time.strftime('%Y-%m-%d')}\"",
        "keep_only_listed: true",
        "tags:",
    ]
    for t in dict.fromkeys(suggested):  # dedup preservando ordine
        lines += [
            f"  - name: \"{t}\"",
            "    action: keep   # keep | drop | merge_into:<canonical>",
            "    synonyms: []",
            "    notes: \"\"",
        ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("tags_reviewed stub scritto", extra={"file_path": str(out), "suggested": len(suggested)})
    return out
