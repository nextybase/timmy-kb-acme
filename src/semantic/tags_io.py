# src/semantic/tags_io.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import csv
from pathlib import Path

from pipeline.exceptions import ConfigError  # per completezza nelle firme/eccezioni
from pipeline.file_utils import ensure_within, safe_write_text


def write_tagging_readme(semantic_dir: Path, logger) -> Path:
    """
    Crea/aggiorna il README rapido per il flusso di tagging nel folder `semantic_dir`.
    Scrittura atomica + guardia path.
    """
    semantic_dir.mkdir(parents=True, exist_ok=True)
    out = semantic_dir / "README_TAGGING.md"
    ensure_within(semantic_dir, out)  # guardia anti path traversal

    content = (
        "# Tag Onboarding (HiTL) – Guida rapida\n\n"
        "1. Apri `tags_raw.csv` e valuta i suggerimenti.\n"
        "2. Compila `tags_reviewed.yaml` (keep/drop/merge).\n"
        "3. Quando pronto, crea/aggiorna `tags.yaml` con i tag canonici + sinonimi.\n"
    )
    safe_write_text(out, content, encoding="utf-8", atomic=True)
    logger.info("README_TAGGING scritto", extra={"file_path": str(out)})
    return out


def write_tags_review_stub_from_csv(
    semantic_dir: Path,
    csv_path: Path,
    logger,
    top_n: int = 100,
) -> Path:
    """
    Genera uno stub `tags_reviewed.yaml` a partire dai suggerimenti in `tags_raw.csv`.

    Il CSV è letto con `csv.reader` per evitare rotture su virgole/quote.
    Si assume che la seconda colonna contenga i suggerimenti (lista separata da virgole);
    viene preso il primo suggerimento non vuoto per ciascuna riga (max `top_n` righe utili).
    """
    suggested: list[str] = []

    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            # salta header se presente
            header = next(reader, None)
            for i, row in enumerate(reader):
                if len(row) < 2:
                    continue
                suggested_str = row[1] or ""
                first = (suggested_str.split(",")[0] or "").strip()
                if first:
                    suggested.append(first)
                if len(suggested) >= top_n:
                    break
    except FileNotFoundError as e:
        raise ConfigError(f"CSV dei tag non trovato: {e}", file_path=str(csv_path)) from e
    except Exception as e:
        raise ConfigError(f"Errore durante la lettura del CSV: {e}", file_path=str(csv_path)) from e

    semantic_dir.mkdir(parents=True, exist_ok=True)
    out = semantic_dir / "tags_reviewed.yaml"
    ensure_within(semantic_dir, out)  # guardia anti path traversal

    lines = [
        "version: 1",
        f'reviewed_at: "{time.strftime("%Y-%m-%d")}"',
        "keep_only_listed: true",
        "tags:",
    ]
    # dedup preservando ordine
    for t in dict.fromkeys(suggested):
        lines += [
            f'  - name: "{t}"',
            "    action: keep   # keep | drop | merge_into:<canonical>",
            "    synonyms: []",
            '    notes: ""',
        ]

    safe_write_text(out, "\n".join(lines) + "\n", encoding="utf-8", atomic=True)
    logger.info(
        "tags_reviewed stub scritto",
        extra={"file_path": str(out), "suggested": len(suggested)},
    )
    return out
