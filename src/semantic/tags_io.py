#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
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
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within
from storage import tags_store
from storage.tags_store import derive_db_path_from_yaml_path
from storage.tags_store import save_tags_reviewed as save_tags_reviewed_db

__all__ = [
    "write_tagging_readme",
    "write_tags_review_stub_from_csv",
    "write_tags_review_from_terms_db",
    "write_tags_reviewed_from_nlp_db",
]


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
    logger.info("semantic.tags.readme_written", extra={"file_path": str(out)})
    return out


def write_tags_review_stub_from_csv(
    semantic_dir: Path,
    csv_path: Path,
    logger: logging.Logger,
    top_n: int = 120,
) -> Path:
    """Genera uno stub di revisione a partire da `tags_raw.csv` e lo salva in SQLite.

    Regole:
    - Richiede lo schema esteso con header `suggested_tags`; se manca viene sollevato ConfigError.
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

            if not header or not isinstance(header, list):
                raise ConfigError(
                    "tags_raw.csv deve usare lo schema esteso con colonna 'suggested_tags'",
                    file_path=str(csv_path),
                )

            try:
                idx_suggestions = header.index("suggested_tags")
            except ValueError as e:
                raise ConfigError(
                    "Colonna 'suggested_tags' mancante: aggiorna tags_raw.csv allo schema esteso",
                    file_path=str(csv_path),
                ) from e

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
    except ConfigError:
        raise
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
        "semantic.tags_review_stub.written",
        extra={"file_path": str(db_path), "suggested": len(suggested)},
    )
    return Path(db_path)


def write_tags_review_from_terms_db(db_path: str | Path, keep_only_listed: bool = True) -> dict[str, Any]:
    """
    Genera (e salva) `tags_reviewed` a partire dal DB NLP (`terms` + `term_aliases`).

    Args:
        db_path: percorso del DB SQLite con le tabelle NLP.
        keep_only_listed: valore da impostare nel payload finale.

    Returns:
        Il dizionario serializzato (version 2) persistito via `save_tags_reviewed`.
    """
    resolved_db_path = Path(db_path).resolve()

    tags_payload: list[dict[str, Any]] = []
    with tags_store.get_conn(str(resolved_db_path)) as conn:
        cur = conn.execute("SELECT id, canonical FROM terms ORDER BY canonical COLLATE NOCASE ASC")
        for term_id, canonical in cur.fetchall():
            synonym_rows = tags_store.list_term_aliases(conn, int(term_id))
            synonyms = [str(alias).strip() for alias in synonym_rows if str(alias).strip()]
            tag_name = str(canonical).strip()
            if not tag_name:
                continue
            tags_payload.append(
                {
                    "name": tag_name,
                    "action": "keep",
                    "synonyms": synonyms,
                    "note": "",
                }
            )

    reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    data: dict[str, Any] = {
        "version": "2",
        "reviewed_at": reviewed_at,
        "keep_only_listed": bool(keep_only_listed),
        "tags": tags_payload,
    }

    tags_store.save_tags_reviewed(str(resolved_db_path), data)
    return data


def write_tags_reviewed_from_nlp_db(
    semantic_dir: Path,
    db_path: Path,
    logger: Any,
    *,
    limit: int = 200,
    min_weight: float = 0.0,
    keep_only_listed: bool = True,
    version: str = "2",
) -> Path:
    """
    Esporta `tags_reviewed.yaml` dai risultati NLP salvati in SQLite (terms / aliases / folder_terms).

    Args:
        semantic_dir: directory `semantic/` del cliente.
        db_path: percorso del DB NLP (tipicamente `semantic/tags.db`).
        logger: logger su cui emettere le informazioni (best-effort).
        limit: numero massimo di tag da includere (ordinati per peso globale).
        min_weight: soglia minima sul peso aggregato per includere un termine.
        keep_only_listed: flag da salvare nel payload finale.
        version: versione del formato `tags_reviewed`.

    Returns:
        Percorso del file YAML scritto.
    """
    semantic_dir = Path(semantic_dir).resolve()
    semantic_dir.mkdir(parents=True, exist_ok=True)
    out_path = semantic_dir / "tags_reviewed.yaml"
    tags_store.ensure_schema_v2(str(db_path))

    tags_payload: list[dict[str, Any]] = []
    keep_only_listed_val = bool(keep_only_listed)
    reviewed_at_val: str | None = None
    used_fallback = False

    try:
        with sqlite3.connect(str(db_path)) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            rows = cur.execute(
                """
                SELECT t.id AS term_id, t.canonical AS canonical, IFNULL(SUM(ft.weight), 0) AS total_weight
                FROM terms t
                LEFT JOIN folder_terms ft
                    ON ft.term_id = t.id
                    AND (ft.status IS NULL OR ft.status = 'keep')
                GROUP BY t.id
                HAVING total_weight >= ?
                ORDER BY total_weight DESC, t.canonical COLLATE NOCASE
                LIMIT ?
                """,
                (float(min_weight), int(limit)),
            ).fetchall()

            for row in rows:
                term_id = int(row["term_id"])
                canonical = str(row["canonical"]).strip()
                if not canonical:
                    continue
                syn_rows = cur.execute(
                    """
                    SELECT alias FROM term_aliases
                    WHERE term_id = ?
                    ORDER BY alias COLLATE NOCASE
                    """,
                    (term_id,),
                ).fetchall()
                synonyms = [str(s["alias"]).strip() for s in syn_rows if str(s["alias"]).strip()]
                tags_payload.append(
                    {
                        "name": canonical,
                        "action": "keep",
                        "synonyms": synonyms,
                        "note": "",
                    }
                )
            if not tags_payload:
                fallback = tags_store.load_tags_reviewed(str(db_path))
                reviewed_at_val = str(fallback.get("reviewed_at") or "") or None
                keep_only_listed_val = bool(fallback.get("keep_only_listed", keep_only_listed_val))
                for item in fallback.get("tags", []):
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    syns = [str(s).strip() for s in item.get("synonyms") or [] if str(s).strip()]
                    tags_payload.append(
                        {
                            "name": name,
                            "action": "keep",
                            "synonyms": syns,
                            "note": str(item.get("note") or ""),
                        }
                    )
                used_fallback = bool(tags_payload)
    except Exception as exc:
        raise ConfigError(f"Impossibile esportare i tag dal DB NLP: {exc}", file_path=str(db_path)) from exc

    payload: dict[str, Any] = {
        "version": version,
        "reviewed_at": reviewed_at_val,
        "keep_only_listed": keep_only_listed_val,
        "tags": tags_payload,
    }

    ensure_within(semantic_dir, out_path)
    yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    safe_write_text(out_path, yaml_text, encoding="utf-8", atomic=True)
    try:
        logger.info(
            "semantic.tags_yaml.exported_from_nlp",
            extra={"file_path": str(out_path), "tags": len(tags_payload)},
        )
        if used_fallback:
            logger.warning(
                "semantic.tags_yaml.fallback_tags_table",
                extra={"file_path": str(out_path), "tags": len(tags_payload)},
            )
    except Exception:
        pass
    return out_path
