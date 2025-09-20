#!/usr/bin/env python3
# src/semantic/tags_io.py
# -*- coding: utf-8 -*-
"""I/O utility per il flusso di tagging (cartella `semantic/`) – Timmy-KB.

Cosa fa il modulo
-----------------
- `write_tagging_readme(semantic_dir, logger) -> Path`
  Crea/aggiorna un README rapido per il processo HiTL di tagging.
  Scrittura atomica e guard-rail STRONG sull'output.

- `write_tags_review_stub_from_csv(semantic_dir, csv_path, logger, top_n=120) -> Path`
  Genera uno stub (persistito in SQLite) a partire da `tags_raw.csv`:
  deduplica e normalizza i suggerimenti (lowercase) fino a `top_n`.
  Lettura consentita solo se il CSV è sotto `semantic_dir` (guardia `ensure_within`).

Sicurezza & I/O
---------------
- Nessun `print()`/`input()` o terminazioni del processo.
- Path-safety: `ensure_within` per output e per vincolare il CSV alla sandbox.
- Scritture atomiche con `safe_write_text` (solo per README).
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within
from storage.tags_store import derive_db_path_from_yaml_path
from storage.tags_store import save_tags_reviewed as save_tags_reviewed_db

__all__ = ["write_tagging_readme", "write_tags_review_stub_from_csv"]


def write_tagging_readme(semantic_dir: Path, logger: logging.Logger) -> Path:
    """Crea/aggiorna il README rapido per il flusso di tagging in `semantic_dir`."""
    semantic_dir = Path(semantic_dir).resolve()
    semantic_dir.mkdir(parents=True, exist_ok=True)

    out = semantic_dir / "README_TAGGING.md"
    ensure_within(semantic_dir, out)

    content = (
        "# Tag Onboarding (HiTL) – Guida rapida\n\n"
        "1. Apri `tags_raw.csv` e valuta i suggerimenti.\n"
        "2. Approva/filtra i tag (keep/drop/merge) e prepara la revisione.\n"
        "3. Procedi con lo stub di revisione per i tag canonici e i sinonimi.\n\n"
        "Nota: `tags_raw.csv` usa lo schema esteso "
        "`relative_path | suggested_tags | entities | keyphrases | score | sources`.\n"
    )
    safe_write_text(out, content, encoding="utf-8", atomic=True)
    logger.info("README_TAGGING scritto", extra={"file_path": str(out)})
    return out


def write_tags_review_stub_from_csv(
    semantic_dir: Path,
    csv_path: Path,
    logger: logging.Logger,
    top_n: int = 120,
) -> Path:
    """Genera uno stub di revisione a partire da `tags_raw.csv` e lo salva in SQLite.

    Compatibilità:
    - Preferisce lo schema esteso con header `suggested_tags`.
    - Se assente, degrada al formato legacy a 2 colonne: [relative_path, suggested_tags].

    Regole:
    - Usa tutti i suggerimenti (split su ',') in lowercase e deduplicati preservando l'ordine.
    - Si ferma quando ha raccolto `top_n` tag unici.
    - Lettura CSV consentita solo se il file è sotto `semantic_dir`.
    """
    semantic_dir = Path(semantic_dir).resolve()
    csv_path = Path(csv_path)

    # Consenti la lettura solo di CSV dentro semantic/: hardening
    from pipeline.path_utils import open_for_read  # import locale

    suggested: list[str] = []
    seen: set[str] = set()

    try:
        with open_for_read(semantic_dir, csv_path, encoding="utf-8") as f:
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

    # Persistenza su SQLite (usiamo lo stesso dict logico del vecchio YAML)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    ensure_within(semantic_dir, yaml_path)
    db_path = derive_db_path_from_yaml_path(yaml_path)

    data = {
        "version": "2",
        "reviewed_at": time.strftime("%Y-%m-%d"),
        "keep_only_listed": True,
        "tags": [{"name": t, "action": "keep", "synonyms": [], "note": ""} for t in suggested],
    }
    save_tags_reviewed_db(db_path, data)
    logger.info(
        "tags_reviewed stub scritto",
        extra={"file_path": str(db_path), "suggested": len(suggested)},
    )
    return Path(db_path)
