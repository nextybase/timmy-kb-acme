# src/semantic/tags_extractor.py
# -*- coding: utf-8 -*-
"""Estrattore tag per PDF "raw" + utilità di ingest locale (Timmy-KB).

Cosa fa il modulo
-----------------
- `copy_local_pdfs_to_raw(src_dir, raw_dir, logger) -> int`
  Copia in modo sicuro i PDF da una sorgente locale dentro `raw/`, con:
  * path-safety (SOFT: `is_safe_subpath` per shortlist/letture),
  * path-safety (STRONG: `ensure_within` prima di ogni write),
  * idempotenza semplice (skip se esiste ed ha stessa dimensione),
  * logging strutturato e propagazione di errori aggregati tramite `PipelineError`.

Schema CSV (compat con orchestratori/tag_onboarding)
----------------------------------------------------
relative_path | suggested_tags | entities | keyphrases | score | sources

Sicurezza & I/O
---------------
- Nessun `print()`/`input()`/uscita del processo.
- Scritture: commit atomiche (`safe_write_text`) e guard-rail STRONG (`ensure_within`).
- Letture: pre-filtro SOFT (`is_safe_subpath`) per evitare path sospetti.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List

from pipeline.exceptions import PipelineError  # eccezione tipizzata per la pipeline
from pipeline.path_utils import ensure_within  # STRONG: SSoT per write/delete
from pipeline.path_utils import is_safe_subpath  # SOFT: pre-check booleano per shortlist/letture
from pipeline.path_utils import normalize_path, sanitize_filename, sorted_paths

__all__ = ["copy_local_pdfs_to_raw"]


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    """Copia PDF da sorgente locale in raw/, con path-safety e idempotenza semplice.

    Regole:
    - SOFT: is_safe_subpath() per filtrare rapidamente path sospetti.
    - STRONG (SSoT): ensure_within(base_dir, <target>) prima di mkdir/copy (write).
    - Idempotenza: se esiste e ha stessa dimensione, salta la copia.
    - Error handling: raccoglie errori di copia e, se presenti, solleva PipelineError a fine ciclo.

    Restituisce:
        Numero di file copiati con successo.

    Raises:
        PipelineError: se almeno una copia fallisce (con elenco dei file in message/extra).
        FileNotFoundError: se la sorgente non è una directory valida.
    """
    src_dir = normalize_path(src_dir)
    raw_dir = normalize_path(raw_dir)
    base_dir = raw_dir.parent  # SSoT: sandbox cliente (output/timmy-kb-<slug>)

    if not src_dir.is_dir():
        raise FileNotFoundError(f"Percorso locale non valido: {src_dir}")

    copied = 0
    failures: list[tuple[Path, Path, str]] = []
    pdfs: List[Path] = [
        p for p in sorted_paths(src_dir.rglob("*"), base=src_dir) if p.is_file() and p.suffix.lower() == ".pdf"
    ]

    for src in pdfs:
        try:
            rel = src.relative_to(src_dir)
        except ValueError:
            rel = Path(sanitize_filename(src.name))

        # Sanitize di ogni componente del path relativo
        rel_sanitized = Path(*[sanitize_filename(p) for p in rel.parts])
        dst = raw_dir / rel_sanitized

        # SOFT: filtro preliminare (non autorizza write)
        if not is_safe_subpath(dst, raw_dir):
            logger.warning("Skip per path non sicuro (soft check)", extra={"file_path": str(dst)})
            continue

        # STRONG (SSoT): autorizzazione write su dir e file di destinazione
        try:
            ensure_within(base_dir, dst.parent)
            ensure_within(base_dir, dst)
        except Exception as e:
            # Qui manteniamo un log e saltiamo: path non valido per policy SSoT
            logger.warning(
                "Skip per path non valido (strong guard)",
                extra={"file_path": str(dst), "error": str(e)},
            )
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                logger.debug("Skip copia (stessa dimensione)", extra={"file_path": str(dst)})
            else:
                shutil.copy2(src, dst)
                logger.info("PDF copiato", extra={"file_path": str(dst)})
                copied += 1
        except (OSError, shutil.Error) as e:
            err_msg = f"{e.__class__.__name__}: {e}"
            failures.append((src, dst, err_msg))
            logger.error(
                "Copia fallita",
                extra={"src": str(src), "dst": str(dst), "error": err_msg},
            )

    if failures:
        # Propaga un errore tipizzato con riepilogo (senza bloccare il log dettagliato per file)
        summary = "; ".join([f"{s} -> {d} ({m})" for s, d, m in failures])
        raise PipelineError(f"Copie PDF fallite: {len(failures)}. Dettagli: {summary}")

    return copied
