#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
import json
import logging
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional, cast

# --- Storage v2 (DB: folders/documents) ---
import storage.tags_store as tags_store

# --- Pipeline infra / Semantic orchestrators ---
from pipeline.config_utils import get_client_config
from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.drive_utils import download_drive_pdfs_to_local, get_drive_service
from pipeline.exceptions import EXIT_CODES, ConfigError, PipelineError
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.logging_utils import get_structured_logger, mask_partial, metrics_scope, tail_path
from pipeline.path_utils import ensure_within  # STRONG guard SSoT
from pipeline.path_utils import (
    ensure_valid_slug,
    ensure_within_and_resolve,
    open_for_read_bytes_selfguard,
)
from semantic.api import build_tags_csv, copy_local_pdfs_to_raw
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv
from storage.tags_store import (
    clear_doc_terms,
    derive_db_path_from_yaml_path,
    ensure_schema_v2,
    get_conn,
    get_documents_by_folder,
    has_doc_terms,
    list_documents,
)
from storage.tags_store import load_tags_reviewed as load_tags_reviewed_db
from storage.tags_store import upsert_document, upsert_folder, upsert_folder_term, upsert_term

yaml: Any | None
try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

_INVALID_CHARS_RE = re.compile(r"[\/:*?\"<>|]")
__all__ = [
    "tag_onboarding_main",
    "validate_tags_reviewed",
    "_validate_tags_reviewed",  # esposto per i test unitari
]


# ───────────────────────────── Helpers UX ────────────────────────────────────────────────────────
def _prompt(msg: str) -> str:
    """Raccoglie input testuale da CLI (abilitato **solo** negli orchestratori)."""
    return input(msg).strip()


# ───────────────────────────── Core: ingest locale ──────────────────────────────────────────────
# Sezione helper duplicati rimossa (copy/CSV delegati)
def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open_for_read_bytes_selfguard(path) as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_pdf_pages(path: Path) -> int | None:
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
    """Crea (se mancano) tutte le cartelle dalla root logica 'raw' fino a `folder_path`.
    Ritorna l'ID della cartella terminale.
    """
    # Normalizza e verifica che folder_path ricada sotto raw_dir (guard forte)
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
        raise PipelineError(
            "upsert_folder_chain: parent_id non determinato",
            file_path=str(folder_path),
        )
    return parent_id


def scan_raw_to_db(raw_dir: str | Path, db_path: str) -> dict[str, int]:
    raw_dir = Path(raw_dir)
    ensure_schema_v2(db_path)

    folders_count = 0
    docs_count = 0
    log = logging.getLogger("tag_onboarding")

    with get_conn(db_path) as conn:
        # registra root 'raw'
        upsert_folder(conn, "raw", None)

        for path in raw_dir.rglob("*"):
            if path.is_dir():
                upsert_folder_chain(conn, raw_dir, path)
                folders_count += 1
                continue
            if path.is_file() and path.suffix.lower() == ".pdf":
                folder_id = upsert_folder_chain(conn, raw_dir, path.parent)
                sha256 = compute_sha256(path)
                pages = get_pdf_pages(path)
                upsert_document(conn, folder_id, path.name, sha256, pages)
                docs_count += 1

    stats: dict[str, int] = {"folders": folders_count, "documents": docs_count}
    log.info("Indicizzazione RAW completata", extra=stats)
    return stats


# =============================
# NLP → DB (doc_terms, terms, folder_terms)
# =============================
# Import locali nel corpo delle funzioni per evitare E402 (ordine import)


def run_nlp_to_db(
    slug: str,
    raw_dir: Path,
    db_path: str,
    *,
    lang: str = "it",
    topn_doc: int = 20,
    topk_folder: int = 30,
    cluster_thr: float = 0.78,
    model: str = "paraphrase-multilingual-MiniLM-L12-v2",
    rebuild: bool = False,
    only_missing: bool = False,
) -> dict[str, Any]:
    ensure_schema_v2(db_path)
    log = logging.getLogger("tag_onboarding")

    with get_conn(db_path) as conn:
        docs = list_documents(conn)
        processed = 0
        saved_items = 0

        # Per risalire al path assoluto del PDF: usare folders.path (tipo 'raw/..')
        def abs_path_for(doc: dict[str, Any]) -> Path:
            folder_id: int | None = None
            folder_id_raw = doc.get("folder_id")
            if folder_id_raw is not None:
                try:
                    folder_id = int(folder_id_raw)
                except (TypeError, ValueError):
                    folder_id = None
            folder_db_path = Path("raw")
            if folder_id is not None:
                row = conn.execute("SELECT path FROM folders WHERE id=?", (folder_id,)).fetchone()
                if row is not None and row[0]:
                    folder_db_path = Path(str(row[0]))
            folder_parts = folder_db_path.parts
            if folder_parts and folder_parts[0] == "raw":
                folder_parts = folder_parts[1:]
            folder_fs_path = raw_dir.joinpath(*folder_parts)
            if folder_id is not None and not folder_fs_path.exists():
                log.warning(
                    "NLP skip: cartella non trovata",
                    extra={"folder_id": folder_id, "folder_path": str(folder_fs_path)},
                )
            filename_val = doc.get("filename")
            if not isinstance(filename_val, str) or not filename_val.strip():
                raise ValueError("filename mancante o non valido")
            candidate = folder_fs_path / filename_val
            return cast(Path, ensure_within_and_resolve(raw_dir, candidate))

        for i, doc in enumerate(docs, start=1):
            doc_id_raw = cast(Any, doc.get("id"))
            try:
                doc_id = int(doc_id_raw)
            except (TypeError, ValueError):
                log.warning("ID documento non valido", extra={"doc": doc})
                continue
            if only_missing and has_doc_terms(conn, doc_id):
                continue
            if rebuild:
                clear_doc_terms(conn, doc_id)

            try:
                pdf_path = abs_path_for(doc)
            except ValueError:
                log.warning("NLP skip: filename non valido", extra={"doc": doc})
                continue
            if not pdf_path.exists():
                log.warning("NLP skip: file non trovato", extra={"file_path": str(pdf_path)})
                continue

            # import lazy per evitare E402
            from nlp.nlp_keywords import (
                extract_text_from_pdf,
                fuse_and_dedup,
                keybert_scores,
                spacy_candidates,
                yake_scores,
            )

            text = extract_text_from_pdf(str(pdf_path))
            cand_spa = spacy_candidates(text, lang=lang)
            sc_y = yake_scores(text, top_k=int(topn_doc) * 2, lang=lang)
            sc_kb = keybert_scores(text, set(cand_spa), model_name=model, top_k=int(topn_doc) * 2)
            fused = fuse_and_dedup(text, cand_spa, sc_y, sc_kb)
            fused.sort(key=lambda x: x[1], reverse=True)
            top_items = [(p, s, "ensemble") for p, s in fused[: int(topn_doc)]]
            if top_items:
                # salva
                from storage.tags_store import save_doc_terms as _save_dt

                _save_dt(conn, doc_id, top_items)
                saved_items += len(top_items)
                processed += 1
            if i % 100 == 0:
                log.info("NLP progress", extra={"processed": i, "documents": len(docs)})

        # Aggregazione per cartella: somma grezza poi normalizzazione max=1
        from nlp.nlp_keywords import topn_by_folder  # import locale prima dell'uso

        folders = conn.execute("SELECT id, path FROM folders ORDER BY id").fetchall()
        phrase_global: dict[str, float] = {}
        folder_stats: dict[int, list[tuple[str, float]]] = {}

        for frow in folders:
            fid = int(frow[0])
            doc_ids = get_documents_by_folder(conn, fid)
            if not doc_ids:
                continue
            q = (
                "SELECT phrase, score FROM doc_terms WHERE document_id IN ("
                + ",".join(["?"] * len(doc_ids))
                + ")"
            )
            rows = conn.execute(q, tuple(doc_ids)).fetchall()
            phrase_agg: dict[str, float] = {}
            for r in rows:
                ph = str(r[0])
                sc = float(r[1])
                phrase_agg[ph] = phrase_agg.get(ph, 0.0) + sc
            if not phrase_agg:
                continue
            maxv = max(phrase_agg.values()) if phrase_agg else 1.0
            if maxv <= 0:
                maxv = 1.0
            norm_items = [(p, (w / maxv)) for p, w in phrase_agg.items()]
            norm_items = topn_by_folder(norm_items, k=int(topk_folder))
            for phrase, weight in norm_items:
                weight_f = float(weight)
                prev = phrase_global.get(phrase)
                if prev is None or weight_f > prev:
                    phrase_global[phrase] = weight_f
            folder_stats[fid] = norm_items
            # log di aggregazione cartella
            log.debug("Aggregazione cartella", extra={"folder_id": fid, "terms": len(norm_items)})

        # Clustering globale per frasi
        global_list = list(phrase_global.items())
        from nlp.nlp_keywords import cluster_synonyms  # import locale

        clusters = cluster_synonyms(global_list, model_name=model, sim_thr=float(cluster_thr))
        if clusters:
            aliases = sum(max(0, len(c.get("synonyms", []) or [])) for c in clusters)
            avg_size = sum(len(c.get("members", []) or []) for c in clusters) / max(
                1, len(clusters)
            )
            log.info(
                "Cluster calcolati",
                extra={"k": len(clusters), "avg_size": avg_size, "aliases": aliases},
            )

        # Persistenza terms/aliases
        phrase_to_tid: dict[str, int] = {}
        terms_count = 0
        alias_count = 0
        for cl in clusters:
            canon = cl["canonical"]
            tid = upsert_term(conn, canon)
            terms_count += 1
            phrase_to_tid[canon] = tid
            for al in cl.get("synonyms", []) or []:
                tags_store.add_term_alias(conn, tid, al)
                alias_count += 1
                phrase_to_tid[al] = tid

        # Map folder items to canonical term_id e salva in folder_terms (aggregato per term)
        folder_terms_count = 0
        for fid, items in folder_stats.items():
            term_agg: dict[int, float] = {}
            for p, w in items:
                tid = phrase_to_tid.get(p)
                if tid is None:
                    continue
                term_agg[tid] = term_agg.get(tid, 0.0) + float(w)
            log.debug(
                "Aggregazione termini per folder", extra={"folder_id": fid, "terms": len(term_agg)}
            )
            for tid, weight in sorted(term_agg.items(), key=lambda kv: kv[1], reverse=True):
                upsert_folder_term(conn, fid, tid, float(weight), status="keep", note=None)
                folder_terms_count += 1

        log.info(
            "NLP completato",
            extra={
                "documents": len(docs),
                "doc_terms": saved_items,
                "terms": terms_count,
                "aliases": alias_count,
                "folders": len(folder_stats),
                "folder_terms": folder_terms_count,
            },
        )

        return {
            "documents": len(docs),
            "doc_terms": saved_items,
            "terms": terms_count,
            "aliases": alias_count,
            "folders": len(folder_stats),
            "folder_terms": folder_terms_count,
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    """Carica e parse un file YAML in modo sicuro."""
    if yaml is None:
        raise ConfigError("PyYAML non disponibile: installa 'pyyaml'.")
    try:
        from pipeline.yaml_utils import yaml_read

        return yaml_read(path.parent, path) or {}
    except OSError as e:
        raise ConfigError(f"Impossibile leggere YAML: {path} ({e})", file_path=str(path)) from e


def _validate_tags_reviewed(data: dict[str, Any]) -> dict[str, Any]:
    """Valida la struttura già caricata da `tags_reviewed.yaml`."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        errors.append("Il file YAML non è una mappa (dict) alla radice.")
        return {"errors": errors, "warnings": warnings}

    for k in ("version", "reviewed_at", "keep_only_listed", "tags"):
        if k not in data:
            errors.append(f"Campo mancante: '{k}'.")

    if "tags" in data and not isinstance(data["tags"], list):
        errors.append("Il campo 'tags' deve essere una lista.")

    if errors:
        return {"errors": errors, "warnings": warnings}

    names_seen_ci = set()
    for idx, item in enumerate(data.get("tags", []), start=1):
        ctx = f"tags[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{ctx}: elemento non è dict.")
            continue

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{ctx}: 'name' mancante o vuoto.")
            continue
        name_stripped = name.strip()
        if len(name_stripped) > 80:
            warnings.append(f"{ctx}: 'name' troppo lungo (>80).")
        if _INVALID_CHARS_RE.search(name_stripped):
            errors.append(f"{ctx}: 'name' contiene caratteri non permessi (/ \\ : * ? \" < > |).")

        name_ci = name_stripped.lower()
        if name_ci in names_seen_ci:
            errors.append(f"{ctx}: 'name' duplicato (case-insensitive): '{name_stripped}'.")
        names_seen_ci.add(name_ci)

        action = item.get("action")
        if not isinstance(action, str) or not action:
            errors.append(f"{ctx}: 'action' mancante.")
        else:
            act = action.strip().lower()
            if act not in ("keep", "drop") and not act.startswith("merge_into:"):
                errors.append(
                    f"{ctx}: 'action' non valida: '{action}'. Usa keep|drop|merge_into:<canonical>."
                )
            if act.startswith("merge_into:"):
                target = act.split(":", 1)[1].strip()
                if not target:
                    errors.append(f"{ctx}: merge_into senza target.")

        syn = item.get("synonyms", [])
        if syn is not None and not isinstance(syn, list):
            errors.append(f"{ctx}: 'synonyms' deve essere lista di stringhe.")
        else:
            for si, s in enumerate(syn or [], start=1):
                if not isinstance(s, str) or not s.strip():
                    errors.append(f"{ctx}: synonyms[{si}] non è stringa valida.")

        if "notes" in item:
            errors.append(f"{ctx}: Chiave non supportata: 'notes'. Usa 'note'.")
        note_val = item.get("note")
        if note_val is not None and not isinstance(note_val, str):
            errors.append(f"{ctx}: 'note' deve essere una stringa.")

    if data.get("keep_only_listed") and not data.get("tags"):
        warnings.append("keep_only_listed=True ma la lista 'tags' è vuota.")

    return {"errors": errors, "warnings": warnings, "count": len(data.get("tags", []))}


def _write_validation_report(
    report_path: Path, result: dict[str, Any], logger: logging.Logger
) -> None:
    ensure_within(report_path.parent, report_path)
    payload = {
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **result,
    }
    safe_write_text(
        report_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        atomic=True,
    )
    logger.info("Report validazione scritto", extra={"file_path": str(report_path)})


def validate_tags_reviewed(slug: str, run_id: Optional[str] = None) -> int:
    """
    Valida `semantic/tags_reviewed.yaml` per un dato cliente.

    Effetti:
      - Scrive `semantic/tags_review_validation.json` con esito, errori e avvisi.
      - Logga il risultato in `logs/<...>/pipeline.log`.

    Exit codes:
      - 0 → validazione OK
      - 1 → errori
      - 2 → solo avvisi
    """
    base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
    semantic_dir = base_dir / "semantic"
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    try:
        ensure_within(base_dir, log_file)
    except ConfigError:
        pass
    logger = get_structured_logger("tag_onboarding.validate", log_file=log_file, run_id=run_id)

    # Controlla esistenza DB; se manca, comportati come prima (errore)
    db_path = derive_db_path_from_yaml_path(yaml_path)
    if not Path(db_path).exists():
        logger.error(
            "Tags DB non trovato",
            extra={"file_path": str(db_path), "file_path_tail": tail_path(Path(db_path))},
        )
        return 1

    try:
        data = load_tags_reviewed_db(db_path)
        result = _validate_tags_reviewed(data)
        report_path = semantic_dir / "tags_review_validation.json"
        _write_validation_report(report_path, result, logger)
    except ConfigError as e:
        logger.error(str(e))
        return 1

    errs = len(result.get("errors", []))
    warns = len(result.get("warnings", []))

    if errs:
        logger.error("Validazione FALLITA", extra={"errors": errs, "warnings": warns})
        return 1
    if warns:
        logger.warning("Validazione con AVVISI", extra={"warnings": warns})
        return 2
    logger.info("Validazione OK", extra={"tags_count": result.get("count", 0)})
    return 0


# ───────────────────────────── MAIN orchestratore ────────────────────────────────────────────────
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
    slug = ensure_valid_slug(
        slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger
    )

    # Context + logger coerenti con orchestratori
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=(source == "drive"),
        run_id=run_id,
    )

    # Path base per il cliente
    base_dir = getattr(context, "base_dir", None) or (
        Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
    )
    ensure_within(base_dir.parent, base_dir)  # base_dir dentro output/
    raw_dir = getattr(context, "raw_dir", None) or (base_dir / "raw")
    semantic_dir = base_dir / "semantic"
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    # Log file sotto la sandbox cliente
    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(base_dir, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger(
        "tag_onboarding", log_file=log_file, context=context, run_id=run_id
    )

    logger.info("Avvio tag_onboarding", extra={"source": source})

    # A) DRIVE (default)
    if source == "drive":
        cfg = get_client_config(context) or {}
        drive_raw_folder_id = cfg.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("drive_raw_folder_id mancante in config.yaml.")
        service = get_drive_service(context)
        with metrics_scope(logger, stage="drive_download", customer=context.slug):
            download_drive_pdfs_to_local(
                service=service,
                remote_root_folder_id=drive_raw_folder_id,
                local_root_dir=raw_dir,
                progress=not non_interactive,
                context=context,
                redact_logs=getattr(context, "redact_logs", False),
            )
        logger.info(
            "Download da Drive completato",
            extra={"folder_id": mask_partial(drive_raw_folder_id)},
        )

    # B) LOCALE
    elif source == "local":
        if not local_path:
            # UX di default: usa direttamente la sandbox RAW del cliente
            local_path = str(raw_dir)
            logger.info(
                "Nessun --local-path fornito: uso RAW del cliente come sorgente",
                extra={"raw": str(raw_dir), "slug": context.slug},
            )
        src_dir = Path(local_path).expanduser().resolve()
        if src_dir == raw_dir.expanduser().resolve():
            logger.info(
                "Sorgente coincidente con RAW: salto fase copia", extra={"raw": str(raw_dir)}
            )
        else:
            with metrics_scope(logger, stage="local_copy", customer=context.slug):
                # Delegato a semantic.api: evita duplicazioni locali
                copied = copy_local_pdfs_to_raw(src_dir, raw_dir, logger)
            logger.info(
                "Copia locale completata",
                extra={"count": copied, "raw_tail": tail_path(raw_dir)},
            )
    else:
        raise ConfigError(f"Sorgente non valida: {source}. Usa 'drive' o 'local'.")

    # Fase 1: CSV in semantic/
    with metrics_scope(logger, stage="emit_csv", customer=context.slug):
        # Delegato a semantic.api: emissione CSV e README tagging
        csv_path = build_tags_csv(context, logger, slug=slug)
    logger.info(
        "Controlla la lista keyword",
        extra={"file_path": str(csv_path), "file_path_tail": tail_path(csv_path)},
    )

    # Checkpoint HiTL
    if non_interactive:
        if not proceed_after_csv:
            logger.info("Stop dopo CSV (non-interattivo, no --proceed).")
            return
    else:
        cont = _prompt(
            "Controlla e approva i tag generati. Sei pronto per proseguire con l'arricchimento semantico? (y/n): "
        ).lower()
        if cont != "y":
            logger.info("Interrotto su richiesta utente, uscita senza arricchimento semantico")
            return

    # Fase 2: stub in semantic/
    with metrics_scope(logger, stage="semantic_stub", customer=context.slug):
        write_tagging_readme(semantic_dir, logger)
        write_tags_review_stub_from_csv(semantic_dir, csv_path, logger)
    logger.info(
        "Arricchimento semantico completato",
        extra={"semantic_dir": str(semantic_dir), "semantic_tail": tail_path(semantic_dir)},
    )


# ───────────────────────────── CLI ───────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    """Costruisce e restituisce il parser CLI per `tag_onboarding`."""
    p = argparse.ArgumentParser(
        description="Tag onboarding (copertura PDF + CSV + checkpoint HiTL + stub semantico)"
    )
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument(
        "--source",
        choices=("drive", "local"),
        default="drive",  # default Drive
        help="Sorgente PDF (default: drive). Usa --source=local per lavorare da una cartella locale.",
    )
    p.add_argument(
        "--local-path",
        type=str,
        help="Percorso locale sorgente dei PDF. Se omesso con --source=local, userà direttamente output/<slug>/raw.",
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
        "--scan-raw", action="store_true", help="Indicizza cartelle e PDF di raw/ nel DB"
    )
    p.add_argument("--raw-dir", type=str, help="Percorso della cartella raw/")
    p.add_argument("--db", type=str, help="Percorso del DB SQLite (tags.db)")
    # NLP → DB
    p.add_argument(
        "--nlp",
        action="store_true",
        help="Esegue estrazione keyword e popolamento DB (doc_terms/terms/folder_terms)",
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
        "--rebuild", action="store_true", help="Ricostruisce doc_terms cancellando quelli esistenti"
    )
    p.add_argument(
        "--only-missing", action="store_true", help="Processa solo documenti senza doc_terms"
    )
    return p.parse_args()


if __name__ == "__main__":
    """Entrypoint CLI orchestratore `tag_onboarding`."""
    args = _parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("tag_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "Errore: in modo non interattivo viene richiesto --slug (o slug posizionale)."
        )
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    try:
        slug = ensure_valid_slug(
            unresolved_slug,
            interactive=not args.non_interactive,
            prompt=_prompt,
            logger=early_logger,
        )
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    # Ramo di sola validazione
    if args.validate_only:
        code = validate_tags_reviewed(slug, run_id=run_id)
        sys.exit(code)

    # Scansione RAW -> DB (schema v2)
    if getattr(args, "scan_raw", False):
        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        raw_dir = Path(args.raw_dir) if args.raw_dir else (base_dir / "raw")
        db_path = str(Path(args.db)) if args.db else str(base_dir / "semantic" / "tags.db")
        stats = scan_raw_to_db(raw_dir, db_path)
        log = get_structured_logger("tag_onboarding", run_id=run_id)
        log.info("Indicizzazione completata", extra=stats)
        sys.exit(0)

    # NLP → DB
    if getattr(args, "nlp", False):
        base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
        raw_dir = Path(args.raw_dir) if args.raw_dir else (base_dir / "raw")
        db_path = str(Path(args.db)) if args.db else str(base_dir / "semantic" / "tags.db")
        lang = args.lang if args.lang != "auto" else "it"
        stats = run_nlp_to_db(
            slug,
            raw_dir,
            db_path,
            lang=lang,
            topn_doc=int(args.topn_doc),
            topk_folder=int(args.topk_folder),
            cluster_thr=float(args.cluster_thr),
            model=str(args.model),
            rebuild=bool(args.rebuild),
            only_missing=bool(args.only_missing),
        )
        log = get_structured_logger("tag_onboarding", run_id=run_id)
        log.info("NLP pipeline terminata", extra=stats)
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
    except (ConfigError, PipelineError) as e:
        logger = get_structured_logger("tag_onboarding", run_id=run_id)
        logger.error(str(e))
        sys.exit(EXIT_CODES.get(type(e).__name__, 1))

# Sezione helper duplicati rimossa (copy/CSV delegati)
