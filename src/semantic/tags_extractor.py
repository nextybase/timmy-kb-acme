# src/semantic/tags_extractor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
import shutil
import logging
from pathlib import Path
from typing import List

from pipeline.path_utils import (
    is_safe_subpath,   # SOFT: pre-check booleano per shortlist/letture
    ensure_within,     # STRONG: SSoT per write/delete
    normalize_path,
    sanitize_filename,
    sorted_paths,
)
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.exceptions import PipelineError     # eccezione tipizzata per la pipeline


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    """
    Copia PDF da sorgente locale in raw/, con path-safety e idempotenza semplice.

    Regole:
    - SOFT: is_safe_subpath() per filtrare rapidamente path sospetti.
    - STRONG (SSoT): ensure_within(base_dir, <target>) prima di mkdir/copy (write).
    - Idempotenza: se esiste e ha stessa dimensione, salta la copia.
    - Error handling: raccoglie errori di copia e, se presenti, solleva PipelineError a fine ciclo.

    Returns:
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
    pdfs: List[Path] = sorted_paths(src_dir.rglob("*.pdf"), base=src_dir)

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
            logger.warning("Skip per path non valido (strong guard)", extra={"file_path": str(dst), "error": str(e)})
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


def emit_tags_csv(raw_dir: Path, csv_path: Path, logger: logging.Logger) -> int:
    """
    Heuristica conservativa: per ogni PDF propone keyword grezze
    da nomi cartelle e filename. HiTL arricchirà in seguito.

    Regole:
    - STRONG (SSoT): ensure_within(base_dir, csv_path[.parent]) prima di scrivere.
    - Scrittura atomica del CSV via safe_write_text.
    """
    raw_dir = normalize_path(raw_dir)
    csv_path = normalize_path(csv_path)
    base_dir = raw_dir.parent  # output/timmy-kb-<slug>

    rows: List[List[str]] = []
    for pdf in sorted_paths(raw_dir.rglob("*.pdf"), base=raw_dir):
        try:
            rel = pdf.relative_to(raw_dir).as_posix()
        except ValueError:
            rel = pdf.name
        parts = [p for p in Path(rel).parts if p]
        base_no_ext = Path(parts[-1]).stem if parts else Path(rel).stem

        # Costruzione candidati: cartelle (lower) + token del filename senza estensione
        candidates = {p.lower() for p in parts[:-1]}
        candidates.update(tok for tok in base_no_ext.replace("_", " ").replace("-", " ").split() if tok)
        rows.append([rel, ", ".join(sorted(candidates))])

    # STRONG (SSoT): autorizza la scrittura nella sandbox cliente
    ensure_within(base_dir, csv_path.parent)
    ensure_within(base_dir, csv_path)

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepara il contenuto CSV in memoria e scrive in modo atomico
    sio = io.StringIO()
    w = csv.writer(sio, lineterminator="\n")
    w.writerow(["relative_path", "suggested_tags"])
    w.writerows(rows)
    data = sio.getvalue()

    safe_write_text(csv_path, data, encoding="utf-8", atomic=True)

    logger.info("Tag grezzi generati", extra={"file_path": str(csv_path), "count": len(rows)})
    return len(rows)
