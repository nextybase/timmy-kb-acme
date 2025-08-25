# src/semantic/tags_io.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import csv
from pathlib import Path
from typing import List

from pipeline.exceptions import ConfigError  # per completezza nelle firme/eccezioni
from pipeline.path_utils import ensure_within
from pipeline.file_utils import safe_write_text


def write_tagging_readme(semantic_dir: Path, logger) -> Path:
    """
    Crea/aggiorna il README rapido per il flusso di tagging nel folder `semantic_dir`.
    Scrittura atomica + guardia path.
    """
    semantic_dir = Path(semantic_dir).resolve()
    semantic_dir.mkdir(parents=True, exist_ok=True)
    out = semantic_dir / "README_TAGGING.md"
    ensure_within(semantic_dir, out)  # guardia anti path traversal

    content = (
        "# Tag Onboarding (HiTL) – Guida rapida\n\n"
        "1. Apri `tags_raw.csv` e valuta i suggerimenti.\n"
        "2. Compila `tags_reviewed.yaml` (keep/drop/merge).\n"
        "3. Quando pronto, crea/aggiorna `tags.yaml` con i tag canonici + sinonimi.\n"
        "\n"
        "_Nota_: `tags_raw.csv` usa lo schema esteso "
        "`relative_path | suggested_tags | entities | keyphrases | score | sources`.\n"
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

    Compatibilità:
    - Preferisce lo schema esteso con header `suggested_tags`.
    - Se assente, degrada a formato legacy a 2 colonne: [relative_path, suggested_tags].

    Regole:
    - Usa tutti i suggerimenti (split su ',') normalizzati in lowercase e deduplicati preservando l'ordine.
    - Si ferma quando ha raccolto `top_n` tag unici.
    - Path-safety: garantita su file di output; lettura CSV consentita solo se sotto `semantic_dir`.
    """
    semantic_dir = Path(semantic_dir).resolve()
    csv_path = Path(csv_path).resolve()

    # Consenti la lettura solo di CSV dentro semantic/: harden per evitare scan errati
    ensure_within(semantic_dir, csv_path)

    suggested: List[str] = []
    seen = set()

    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)

            # Individua l'indice della colonna suggerimenti
            idx_suggestions = 1  # fallback legacy
            if header and isinstance(header, list):
                try:
                    idx_suggestions = header.index("suggested_tags")
                except ValueError:
                    # header diverso o assente -> mantieni fallback
                    pass

            for row in reader:
                if idx_suggestions >= len(row):
                    continue
                raw_field = row[idx_suggestions] or ""
                # split su virgola, trim e normalizza lowercase
                tokens = [t.strip().lower() for t in raw_field.split(",") if t.strip()]
                for tok in tokens:
                    if tok not in seen:
                        seen.add(tok)
                        suggested.append(tok)
                        if len(seen) >= int(top_n):
                            break
                if len(seen) >= int(top_n):
                    break

    except FileNotFoundError as e:
        raise ConfigError(f"CSV dei tag non trovato: {e}", file_path=str(csv_path)) from e
    except Exception as e:
        raise ConfigError(f"Errore durante la lettura del CSV: {e}", file_path=str(csv_path)) from e

    # Preparazione output YAML (stub di review)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    out = semantic_dir / "tags_reviewed.yaml"
    ensure_within(semantic_dir, out)  # guardia anti path traversal

    lines = [
        "version: 1",
        f'reviewed_at: "{time.strftime("%Y-%m-%d")}"',
        "keep_only_listed: true",
        "tags:",
    ]
    # `suggested` è già deduplicato preservando l'ordine
    for t in suggested:
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
