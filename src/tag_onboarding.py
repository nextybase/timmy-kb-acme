#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# SPDX-License-Identifier: GPL-3.0-only

# src/tag_onboarding.py

"""

Orchestratore: Tag Onboarding (HiTL)



Step intermedio tra `pre_onboarding` e `onboarding_full`.

A partire dai PDF grezzi in `raw/`, produce un CSV con i tag suggeriti e

(dopo conferma) genera gli stub per la revisione semantica.



Punti chiave:

- Niente `print()` → logging strutturato.

- Path-safety STRONG con `ensure_within`.

- Scritture atomiche centralizzate con `safe_write_text`.

- Integrazione Google Drive supportata (default: Drive).

- Checkpoint HiTL tra CSV e generazione stub semantici.

"""


from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional, cast

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger, tail_path
from pipeline.path_utils import (  # STRONG guard SSoT
    ensure_valid_slug,
    ensure_within,
    ensure_within_and_resolve,
    iter_safe_paths,
    open_for_read_bytes_selfguard,
)
from semantic import nlp_runner
from semantic.tags_validator import validate_tags_reviewed as validate_tags_payload
from semantic.tags_validator import write_validation_report as write_validation_report_payload
from semantic.types import ClientContextProtocol
from storage.tags_store import clear_doc_terms, derive_db_path_from_yaml_path, ensure_schema_v2, get_conn, has_doc_terms
from storage.tags_store import load_tags_reviewed as load_tags_reviewed_db
from storage.tags_store import upsert_document, upsert_folder
from tag_onboarding_context import ContextResources, prepare_context
from tag_onboarding_raw import copy_from_local, download_from_drive
from tag_onboarding_semantic import emit_csv_phase, emit_stub_phase


def _prompt(msg: str) -> str:
    """Raccoglie input testuale da CLI (abilitato **solo** negli orchestratori)."""

    return input(msg).strip()


# ───────────────────────────── Core: ingest locale ───────────────────────────────────


def compute_sha256(path: Path) -> str:
    """SHA-256 streaming del file (chunk 8 KiB) con guardie di lettura sicure."""

    h = hashlib.sha256()

    with open_for_read_bytes_selfguard(path) as f:

        for chunk in iter(lambda: f.read(8192), b""):

            h.update(chunk)

    return h.hexdigest()


def get_pdf_pages(path: Path) -> int | None:
    """Prova a contare le pagine PDF usando pypdf, se disponibile."""

    try:

        import importlib

        module = importlib.import_module("pypdf")

        pdf_reader = getattr(module, "PdfReader", None)

    except Exception:  # pragma: no cover

        return None

    if pdf_reader is None:

        return None

    try:

        reader = cast(Any, pdf_reader)(str(path))

        return len(getattr(reader, "pages", []) or [])

    except Exception:

        return None


def upsert_folder_chain(conn: Any, raw_dir: Path, folder_path: Path) -> int:
    """Crea (se mancano) tutte le cartelle da 'raw' fino a `folder_path`.



    Ritorna l'ID della cartella terminale.

    """

    # Normalizza e verifica che folder_path sia sotto raw_dir (guard forte)

    raw_dir = Path(raw_dir).resolve()

    folder_path = Path(folder_path).resolve()

    ensure_within(raw_dir, folder_path)

    rel = folder_path.relative_to(raw_dir)

    # Inserisci/aggiorna la root logica 'raw'

    parent_id: Optional[int] = upsert_folder(conn, "raw", None)

    current_db_path = "raw"

    # Crea la catena discendente: raw/part1[/part2...]

    for part in rel.parts:

        current_db_path = f"{current_db_path}/{part}".replace("\\", "/")

        parent_db_path = str(Path(current_db_path).parent).replace("\\", "/")

        if parent_db_path == ".":

            parent_db_path = "raw"

        parent_id = upsert_folder(conn, current_db_path, parent_db_path)

    if parent_id is None:

        raise PipelineError("upsert_folder_chain: parent_id non determinato", file_path=str(folder_path))

    return parent_id


def scan_raw_to_db(
    raw_dir: str | Path,
    db_path: str | Path,
    *,
    base_dir: Path | None = None,
) -> dict[str, int]:
    """Indicizza cartelle e PDF di `raw/` dentro il DB (schema v2)."""

    base_dir_path = Path(base_dir).resolve() if base_dir is not None else Path(raw_dir).resolve().parent

    raw_dir_path = ensure_within_and_resolve(base_dir_path, raw_dir)

    db_path_path = ensure_within_and_resolve(base_dir_path, db_path)

    ensure_schema_v2(str(db_path_path))

    folders_count = 0

    docs_count = 0

    log = get_structured_logger("tag_onboarding")

    with get_conn(str(db_path_path)) as conn:

        # registra root 'raw'

        upsert_folder(conn, "raw", None)

        for path in iter_safe_paths(raw_dir_path, include_dirs=True, include_files=True):

            if path.is_dir():

                upsert_folder_chain(conn, raw_dir_path, path)

                folders_count += 1

                continue

            if path.is_file() and path.suffix.lower() == ".pdf":

                folder_id = upsert_folder_chain(conn, raw_dir_path, path.parent)

                sha256_new = compute_sha256(path)

                pages = get_pdf_pages(path)

                row = conn.execute(
                    "SELECT id, sha256 FROM documents WHERE folder_id=? AND filename=?",
                    (folder_id, path.name),
                ).fetchone()

                prev_id = int(row["id"]) if row and row["id"] is not None else None

                prev_sha = str(row["sha256"]) if row and row["sha256"] is not None else None

                if prev_id is not None and prev_sha and prev_sha != sha256_new and has_doc_terms(conn, prev_id):

                    clear_doc_terms(conn, prev_id)

                    log.info(
                        "tag_onboarding.doc_terms.invalidated",
                        extra={"file_name": path.name, "folder_id": folder_id},
                    )

                upsert_document(conn, folder_id, path.name, sha256_new, pages)

                docs_count += 1

    stats: dict[str, int] = {"folders": folders_count, "documents": docs_count}

    log.info("cli.tag_onboarding.scan_completed", extra=stats)

    return stats


# ============================= NLP ? DB (doc_terms / terms / folder_terms) =======================


def run_nlp_to_db(
    slug: str,
    raw_dir: Path | str,
    db_path: str | Path,
    *,
    base_dir: Path | None = None,
    lang: str = "it",
    topn_doc: int = 20,
    topk_folder: int = 30,
    cluster_thr: float = 0.78,
    model: str = "paraphrase-multilingual-MiniLM-L12-v2",
    rebuild: bool = False,
    only_missing: bool = False,
    max_workers: int | None = None,
    worker_batch_size: int = 4,
    enable_entities: bool = True,
) -> dict[str, Any]:
    """Esegue estrazione keyword, clustering e aggregazione per cartella."""

    base_dir_path = Path(base_dir).resolve() if base_dir is not None else Path(raw_dir).resolve().parent

    raw_dir_path = ensure_within_and_resolve(base_dir_path, raw_dir)

    db_path_path = ensure_within_and_resolve(base_dir_path, db_path)

    ensure_schema_v2(str(db_path_path))

    log = get_structured_logger("tag_onboarding")

    worker_batch_size = max(1, int(worker_batch_size))

    if max_workers is None:

        cpu_count = os.cpu_count() or 1

        worker_count = max(1, min(32, cpu_count))

    else:

        worker_count = max(1, int(max_workers))

    if worker_count > 1:

        log.info(
            "cli.tag_onboarding.nlp_executor_configured",
            extra={"workers": worker_count, "batch_size": worker_batch_size},
        )

    with get_conn(str(db_path_path)) as conn:

        stats = nlp_runner.run_doc_terms_pipeline(
            conn,
            raw_dir_path=raw_dir_path,
            lang=lang,
            topn_doc=topn_doc,
            topk_folder=topk_folder,
            cluster_thr=cluster_thr,
            model=model,
            only_missing=only_missing,
            rebuild=rebuild,
            worker_count=worker_count,
            worker_batch_size=worker_batch_size,
            logger=log,
        )

    if enable_entities:
        try:
            from semantic.entities_runner import run_doc_entities_pipeline

            ent_stats = run_doc_entities_pipeline(
                base_dir=base_dir_path,
                raw_dir=raw_dir_path,
                semantic_dir=base_dir_path / "semantic",
                db_path=db_path_path,
                logger=log,
            )
            stats = {**stats, **ent_stats}
        except Exception as exc:  # pragma: no cover
            log.warning("tag_onboarding.entities.failed", extra={"error": str(exc)})

    enriched_stats = {
        **stats,
        "workers": worker_count,
        "batch_size": worker_batch_size,
    }

    log.info("cli.tag_onboarding.nlp_completed", extra=enriched_stats)

    return enriched_stats


def validate_tags_reviewed(slug: str, run_id: Optional[str] = None) -> int:
    """Valida `semantic/tags_reviewed.yaml` sfruttando il contesto cliente."""

    context = ClientContext.load(
        slug=slug,
        interactive=False,
        require_env=False,
        run_id=run_id,
        stage="validate",
    )

    base_attr = getattr(context, "base_dir", None) or getattr(context, "repo_root_dir", None)

    if base_attr is None:

        base_attr = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"

    base_dir = Path(base_attr).resolve()

    semantic_attr = getattr(context, "semantic_dir", None)

    semantic_candidate = Path(semantic_attr) if semantic_attr is not None else (base_dir / "semantic")

    semantic_dir = ensure_within_and_resolve(base_dir, semantic_candidate)

    yaml_candidate = semantic_dir / "tags_reviewed.yaml"

    yaml_path = ensure_within_and_resolve(semantic_dir, yaml_candidate)

    report_candidate = semantic_dir / "tags_review_validation.json"

    report_path = ensure_within_and_resolve(semantic_dir, report_candidate)

    db_candidate = Path(derive_db_path_from_yaml_path(yaml_path))

    db_path = ensure_within_and_resolve(base_dir, db_candidate)

    log_dir = ensure_within_and_resolve(base_dir, base_dir / LOGS_DIR_NAME)

    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = ensure_within_and_resolve(log_dir, log_dir / LOG_FILE_NAME)

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger(
        "tag_onboarding.validate",
        log_file=log_file,
        context=context,
        run_id=run_id,
    )

    if not db_path.exists():

        logger.error(
            "cli.tag_onboarding.db_missing",
            extra={"file_path": str(db_path), "file_path_tail": tail_path(db_path)},
        )

        return 1

    try:

        data = load_tags_reviewed_db(str(db_path))

        result = validate_tags_payload(data)

        write_validation_report_payload(report_path, result, logger)
        logger.info(
            "cli.tag_onboarding.report_written",
            extra={"file_path": str(report_path)},
        )

    except ConfigError as e:

        logger.error(str(e))

        return 1

    errs = len(result.get("errors", []))

    warns = len(result.get("warnings", []))

    if errs:

        logger.error("cli.tag_onboarding.validation_failed", extra={"errors": errs, "warnings": warns})

        return 1

    if warns:

        logger.warning("cli.tag_onboarding.validation_warn", extra={"warnings": warns})

        return 2

    logger.info("cli.tag_onboarding.validation_ok", extra={"tags_count": result.get("count", 0)})

    return 0


def _should_proceed(*, non_interactive: bool, proceed_after_csv: bool, logger: logging.Logger) -> bool:
    """Checkpoint HiTL: decide se proseguire con la generazione degli stub."""

    if non_interactive:

        if not proceed_after_csv:

            logger.info("cli.tag_onboarding.stop_after_csv")

            return False

        return True

    cont = _prompt(
        "Controlla e approva i tag generati. " "Sei pronto per proseguire con l'arricchimento semantico? (y/n): "
    ).lower()

    if cont != "y":

        logger.info("cli.tag_onboarding.user_aborted")

        return False

    return True


def tag_onboarding_main(
    slug: str,
    *,
    source: str = "drive",  # default Drive (puoi passare --source=local)
    local_path: Optional[str] = None,
    non_interactive: bool = False,
    proceed_after_csv: bool = False,
    run_id: Optional[str] = None,
) -> None:
    """Orchestratore della fase di *Tag Onboarding*."""

    early_logger = get_structured_logger("tag_onboarding", run_id=run_id)

    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # Context + logger coerenti con orchestratori

    resources: ContextResources = prepare_context(
        slug=slug,
        non_interactive=non_interactive,
        run_id=run_id,
        require_env=(source == "drive"),
    )

    context = resources.context

    raw_dir = resources.raw_dir

    semantic_dir = resources.semantic_dir

    logger = resources.logger

    logger.info("cli.tag_onboarding.started", extra={"slug": slug, "source": source})

    # Sorgente di PDF

    if source == "drive":

        download_from_drive(context, logger, raw_dir=raw_dir, non_interactive=non_interactive)

    # B) LOCALE

    elif source == "local":

        copy_from_local(
            logger,
            raw_dir=raw_dir,
            local_path=local_path,
            non_interactive=non_interactive,
            context=context,
        )

    else:

        raise ConfigError(f"Sorgente non valida: {source}. Usa 'drive' o 'local'.")

    # Fase 1: CSV in semantic/

    csv_path = emit_csv_phase(context, logger, slug=slug, raw_dir=raw_dir, semantic_dir=semantic_dir)

    # Checkpoint HiTL

    if not _should_proceed(non_interactive=non_interactive, proceed_after_csv=proceed_after_csv, logger=logger):

        return

    # Fase 2: stub in semantic/

    emit_stub_phase(semantic_dir, csv_path, logger, context=context)


# ───────────────────────────── CLI ──────────────────────────────────────────────────────────────


def _resolve_cli_paths(
    context: ClientContextProtocol | ClientContext,
    *,
    raw_override: str | None,
    db_override: str | None,
) -> tuple[Path, Path, Path, Path]:
    """Calcola i percorsi CLI garantendo path-safety rispetto al contesto cliente."""

    base_attr = getattr(context, "base_dir", None) or getattr(context, "repo_root_dir", None)

    if base_attr is None:

        base_candidate = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{context.slug}"

    else:

        base_candidate = Path(base_attr)

    base_dir = base_candidate.resolve()

    raw_attr = Path(raw_override) if raw_override else getattr(context, "raw_dir", None)

    if raw_attr is None:

        raw_candidate = base_dir / "raw"

    else:

        raw_candidate = Path(raw_attr)

    semantic_attr = getattr(context, "semantic_dir", None)

    if semantic_attr is None:

        semantic_candidate = base_dir / "semantic"

    else:

        semantic_candidate = Path(semantic_attr)

    raw_dir = ensure_within_and_resolve(base_dir, raw_candidate)

    semantic_dir = ensure_within_and_resolve(base_dir, semantic_candidate)

    db_candidate = Path(db_override) if db_override else (semantic_dir / "tags.db")

    db_path = ensure_within_and_resolve(base_dir, db_candidate)

    return base_dir, raw_dir, db_path, semantic_dir


def _parse_args() -> argparse.Namespace:
    """Costruisce e restituisce il parser CLI per `tag_onboarding`."""

    p = argparse.ArgumentParser(description=("Tag onboarding (copertura PDF + CSV + checkpoint HiTL + stub semantico)"))

    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")

    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")

    p.add_argument(
        "--source",
        choices=("drive", "local"),
        default="drive",
        help=("Sorgente PDF (default: drive). Usa --source=local per lavorare da una " "cartella locale."),
    )

    p.add_argument(
        "--local-path",
        type=str,
        help=(
            "Percorso locale sorgente dei PDF. Se omesso con --source=local, userà " "direttamente output/<slug>/raw."
        ),
    )

    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")

    p.add_argument(
        "--proceed",
        action="store_true",
        help="In non-interattivo: prosegue anche alla fase 2 (stub semantico)",
    )

    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Esegue solo la validazione di tags_reviewed.yaml",
    )

    # Scansione RAW -> DB (opzionale)

    p.add_argument(
        "--scan-raw",
        action="store_true",
        help="Indicizza cartelle e PDF di raw/ nel DB",
    )

    p.add_argument("--raw-dir", type=str, help="Percorso della cartella raw/")

    p.add_argument("--db", type=str, help="Percorso del DB SQLite (tags.db)")

    # NLP → DB

    p.add_argument(
        "--nlp",
        action="store_true",
        help="Estrae keyword e popola DB (doc_terms/terms/folder_terms)",
    )

    p.add_argument(
        "--lang",
        type=str,
        default="it",
        choices=("it", "en", "auto"),
        help="Lingua testo (it|en|auto)",
    )

    p.add_argument("--topn-doc", type=int, default=20, help="Top-N doc_terms per documento")

    p.add_argument("--topk-folder", type=int, default=30, help="Top-K termini per cartella")

    p.add_argument(
        "--cluster-thr",
        type=float,
        default=0.78,
        help="Soglia similitudine per clustering (cosine)",
    )

    p.add_argument(
        "--model",
        type=str,
        default="paraphrase-multilingual-MiniLM-L12-v2",
        help="Modello SentenceTransformer",
    )

    p.add_argument(
        "--nlp-workers",
        type=int,
        default=None,
        help="Numero di worker paralleli per l'estrazione NLP (default: auto, minimo 1).",
    )

    p.add_argument(
        "--nlp-batch-size",
        type=int,
        default=4,
        help="Dimensione chunk per il mapping parallelo (default: 4).",
    )

    p.add_argument(
        "--nlp-no-parallel",
        action="store_true",
        help="Disattiva l'esecuzione parallela forzando 1 worker (utile per debug).",
    )

    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Ricostruisce doc_terms cancellando quelli esistenti",
    )

    p.add_argument(
        "--only-missing",
        action="store_true",
        help="Processa solo documenti senza doc_terms",
    )

    return p.parse_args()


if __name__ == "__main__":

    """Entrypoint CLI orchestratore `tag_onboarding`."""

    args = _parse_args()

    run_id = uuid.uuid4().hex

    early_logger = get_structured_logger("tag_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug

    if not unresolved_slug and args.non_interactive:

        early_logger.error("cli.tag_onboarding.missing_slug")

        sys.exit(exit_code_for(ConfigError("Missing slug in non-interactive mode")))

    try:

        slug = ensure_valid_slug(
            unresolved_slug,
            interactive=not args.non_interactive,
            prompt=_prompt,
            logger=early_logger,
        )

    except ConfigError as exc:

        sys.exit(exit_code_for(exc))

    # Ramo di sola validazione

    if args.validate_only:

        code = validate_tags_reviewed(slug, run_id=run_id)

        sys.exit(code)

    # Scansione RAW -> DB (schema v2)

    if getattr(args, "scan_raw", False):

        ctx = ClientContext.load(
            slug=slug,
            interactive=False,
            require_env=False,
            run_id=run_id,
            stage="scan_raw",
        )

        base_dir, raw_dir, db_path, _ = _resolve_cli_paths(
            ctx,
            raw_override=args.raw_dir,
            db_override=args.db,
        )

        stats = scan_raw_to_db(raw_dir, db_path, base_dir=base_dir)

        log = get_structured_logger("tag_onboarding", run_id=run_id, context=ctx)

        log.info("cli.tag_onboarding.scan_completed", extra=stats)

        sys.exit(0)

    # NLP → DB

    if getattr(args, "nlp", False):

        ctx = ClientContext.load(
            slug=slug,
            interactive=False,
            require_env=False,
            run_id=run_id,
            stage="nlp",
        )

        base_dir, raw_dir, db_path, _ = _resolve_cli_paths(
            ctx,
            raw_override=args.raw_dir,
            db_override=args.db,
        )

        lang = args.lang if args.lang != "auto" else "it"

        worker_override = 1 if args.nlp_no_parallel else args.nlp_workers

        stats = run_nlp_to_db(
            slug,
            raw_dir,
            db_path,
            base_dir=base_dir,
            lang=lang,
            topn_doc=int(args.topn_doc),
            topk_folder=int(args.topk_folder),
            cluster_thr=float(args.cluster_thr),
            model=str(args.model),
            rebuild=bool(args.rebuild),
            only_missing=bool(args.only_missing),
            max_workers=worker_override if worker_override is not None else None,
            worker_batch_size=int(args.nlp_batch_size),
        )

        log = get_structured_logger("tag_onboarding", run_id=run_id, context=ctx)

        log.info("cli.tag_onboarding.nlp_completed", extra=stats)

        sys.exit(0)

    try:

        tag_onboarding_main(
            slug=slug,
            source=args.source,
            local_path=args.local_path,
            non_interactive=args.non_interactive,
            proceed_after_csv=bool(args.proceed),
            run_id=run_id,
        )

        sys.exit(0)

    except KeyboardInterrupt:

        sys.exit(130)

    except PipelineError as exc:

        logger = get_structured_logger("tag_onboarding", run_id=run_id)

        logger.exception(
            "cli.tag_onboarding.failed",
            extra={"slug": slug, "error": str(exc), "exit_code": exit_code_for(exc)},
        )

        sys.exit(exit_code_for(exc))

    except Exception as exc:  # noqa: BLE001

        logger = get_structured_logger("tag_onboarding", run_id=run_id)

        logger.exception(
            "cli.tag_onboarding.failed",
            extra={"slug": slug, "error": str(exc), "exit_code": exit_code_for(PipelineError(str(exc)))},
        )

        sys.exit(exit_code_for(PipelineError(str(exc))))


# Sezione helper duplicati rimossa (copy/CSV delegati)
