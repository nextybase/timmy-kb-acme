#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# src/tag_onboarding.py
"""
Orchestratore: Tag Onboarding (HiTL)
Step intermedio tra pre_onboarding e onboarding_full.

Fase 1:
- Scarica/copia PDF in output/timmy-kb-<slug>/raw/
- Genera output/timmy-kb-<slug>/semantic/tags_raw.csv
- Checkpoint HiTL: chiedi se proseguire

Fase 2 (se confermato o --proceed):
- Genera README_TAGGING.md e tags_reviewed.yaml (stub) in semantic/

Validazione standalone:
- --validate-only valida tags_reviewed.yaml e scrive tags_review_validation.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, List

# ── Pipeline infra (coerente con gli orchestratori) ──────────────────────────
from pipeline.logging_utils import (
    get_structured_logger,
    mask_partial,
    tail_path,
)
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    EXIT_CODES,
)
from pipeline.context import ClientContext
from pipeline.config_utils import get_client_config
from pipeline.drive_utils import get_drive_service, download_drive_pdfs_to_local
from pipeline.constants import (
    LOGS_DIR_NAME,
    LOG_FILE_NAME,
    RAW_DIR_NAME,
)
from pipeline.path_utils import (
    ensure_valid_slug,
    is_safe_subpath,
    sanitize_filename,
    sorted_paths,
    ensure_within,  # ← guardia STRONG ora qui (SSoT)
)
from pipeline.file_utils import safe_write_text  # ← scritture atomiche
from pipeline.env_utils import compute_redact_flag

# Stub/README tagging centralizzati
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv

# opzionale: PyYAML per validazione
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


# ─────────────────────────── Helpers UX ───────────────────────────
def _prompt(msg: str) -> str:
    return input(msg).strip()


# ───────────────────────────── Core: ingest locale ───────────────────────────
def _copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger) -> int:
    src_dir = src_dir.expanduser().resolve()
    raw_dir = raw_dir.expanduser().resolve()

    if not src_dir.is_dir():
        raise ConfigError(f"Percorso locale non valido: {src_dir}", file_path=str(src_dir))

    count = 0
    pdfs: List[Path] = sorted_paths(src_dir.rglob("*.pdf"), base=src_dir)

    for src in pdfs:
        try:
            rel = src.relative_to(src_dir)
        except Exception:
            rel = Path(sanitize_filename(src.name))

        rel_sanitized = Path(*[sanitize_filename(p) for p in rel.parts])
        dst = raw_dir / rel_sanitized

        if not is_safe_subpath(dst, raw_dir):
            logger.warning("Skip per path non sicuro", extra={"file_path": str(dst), "file_path_tail": tail_path(dst)})
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


# ──────────────────────────────── CSV (Fase 1) ───────────────────────────────
def _emit_tags_csv(raw_dir: Path, csv_path: Path, logger) -> int:
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

    ensure_within(csv_path.parent, csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # Scrittura robusta via csv.writer su buffer + commit atomico
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["relative_path", "suggested_tags"])
    for rel, tags in rows:
        writer.writerow([rel, tags])
    safe_write_text(csv_path, buf.getvalue(), encoding="utf-8", atomic=True)

    logger.info("Tag grezzi generati", extra={"file_path": str(csv_path), "count": len(rows)})
    return len(rows)


# ───────────────────────────── Validatore YAML ───────────────────────────────
_INVALID_CHARS_RE = re.compile(r'[\/\\:\*\?"<>\|]')

def _load_yaml(path: Path):
    if yaml is None:
        raise ConfigError("PyYAML non disponibile: installa 'pyyaml'.")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise ConfigError(f"Impossibile leggere/parsing YAML: {path} ({e})")

def _validate_tags_reviewed(data: dict) -> dict:
    errors, warnings = [], []

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
                errors.append(f"{ctx}: 'action' non valida: '{action}'. Usa keep|drop|merge_into:<canonical>.")
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

        notes = item.get("notes", "")
        if notes is not None and not isinstance(notes, str):
            errors.append(f"{ctx}: 'notes' deve essere una stringa.")

    if data.get("keep_only_listed") and not data.get("tags"):
        warnings.append("keep_only_listed=True ma la lista 'tags' è vuota.")

    return {"errors": errors, "warnings": warnings, "count": len(data.get("tags", []))}

def _write_validation_report(report_path: Path, result: dict, logger):
    ensure_within(report_path.parent, report_path)
    payload = {
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **result,
    }
    safe_write_text(report_path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", atomic=True)
    logger.info("Report validazione scritto", extra={"file_path": str(report_path)})


def validate_tags_reviewed(slug: str, run_id: Optional[str] = None) -> int:
    # Fallback robusto: calcoliamo la base anche se il contesto non è disponibile
    base_dir = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
    semantic_dir = base_dir / "semantic"
    yaml_path = semantic_dir / "tags_reviewed.yaml"
    log_file = base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    logger = get_structured_logger("tag_onboarding.validate", log_file=log_file, run_id=run_id)

    if not yaml_path.exists():
        logger.error("File tags_reviewed.yaml non trovato", extra={"file_path": str(yaml_path), "file_path_tail": tail_path(yaml_path)})
        return 1

    try:
        data = _load_yaml(yaml_path)
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


# ────────────────────────────── MAIN orchestratore ───────────────────────────
def tag_onboarding_main(
    slug: str,
    *,
    source: str = "drive",          # 'drive' | 'local'
    local_path: Optional[str] = None,
    non_interactive: bool = False,
    proceed_after_csv: bool = False,
    run_id: Optional[str] = None,
) -> None:
    early_logger = get_structured_logger("tag_onboarding", run_id=run_id)
    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # Context + logger coerenti con orchestratori
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=(source == "drive"),
        run_id=run_id,
    )
    # Guardia di uniformità redaction (se un orchestratore legacy non l'avesse impostata)
    if not hasattr(context, "redact_logs"):
        context.redact_logs = compute_redact_flag(getattr(context, "env", {}), getattr(context, "log_level", "INFO"))

    # Log file sotto la root cliente
    repo_root = getattr(context, "repo_root_dir", None)
    if repo_root is None:
        # Fallback se il campo non fosse ancora presente nel contesto
        repo_root = Path(__file__).resolve().parents[2] / "output" / f"timmy-kb-{slug}"
    log_file = repo_root / LOGS_DIR_NAME / LOG_FILE_NAME
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("tag_onboarding", log_file=log_file, context=context, run_id=run_id)

    # Path base
    base_dir = repo_root
    raw_dir = base_dir / RAW_DIR_NAME
    semantic_dir = base_dir / "semantic"
    raw_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)

    logger.info("🚀 Avvio tag_onboarding", extra={"source": source})

    # A) DRIVE
    if source == "drive":
        cfg = get_client_config(context) or {}
        drive_raw_folder_id = cfg.get("drive_raw_folder_id")
        if not drive_raw_folder_id:
            raise ConfigError("drive_raw_folder_id mancante in config.yaml.")
        service = get_drive_service(context)
        download_drive_pdfs_to_local(
            service=service,
            remote_root_folder_id=drive_raw_folder_id,
            local_root_dir=raw_dir,
            progress=not non_interactive,
            context=context,
            redact_logs=context.redact_logs,
        )
        logger.info("✅ Download da Drive completato", extra={"folder_id": mask_partial(drive_raw_folder_id)})

    # B) LOCALE
    elif source == "local":
        if not local_path:
            if non_interactive:
                raise ConfigError("In modalità non-interattiva è richiesto --local-path per source=local.")
            local_path = _prompt("Percorso cartella PDF: ").strip()
        copied = _copy_local_pdfs_to_raw(Path(local_path), raw_dir, logger)
        logger.info("✅ Copia locale completata", extra={"count": copied, "raw_tail": tail_path(raw_dir)})
    else:
        raise ConfigError(f"Sorgente non valida: {source}. Usa 'drive' o 'local'.")

    # Fase 1: CSV in semantic/
    csv_path = semantic_dir / "tags_raw.csv"
    _emit_tags_csv(raw_dir, csv_path, logger)
    logger.info("⚠️  Controlla la lista keyword", extra={"file_path": str(csv_path), "file_path_tail": tail_path(csv_path)})

    # Checkpoint HiTL
    if non_interactive:
        if not proceed_after_csv:
            logger.info("Stop dopo CSV (non-interattivo, no --proceed).")
            return
    else:
        cont = _prompt("Vuoi proseguire con arricchimento semantico? (y/n): ").lower()
        if cont != "y":
            logger.info("Interrotto su richiesta utente, uscita senza arricchimento semantico")
            return

    # Fase 2: stub in semantic/
    write_tagging_readme(semantic_dir, logger)
    write_tags_review_stub_from_csv(semantic_dir, csv_path, logger)
    logger.info("✅ Arricchimento semantico completato", extra={"semantic_dir": str(semantic_dir), "semantic_tail": tail_path(semantic_dir)})


# ─────────────────────────────────── CLI ─────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tag onboarding (download/copertura PDF + CSV + checkpoint HiTL + stub semantico)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--source", choices=("drive", "local"), default="drive", help="Sorgente PDF")
    p.add_argument("--local-path", type=str, help="Percorso locale (richiesto se --source=local in non-interattivo)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--proceed", action="store_true", help="In non-interattivo: prosegue anche alla fase 2 (stub semantico)")
    p.add_argument("--validate-only", action="store_true", help="Esegue solo la validazione di tags_reviewed.yaml")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("tag_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
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

    try:
        tag_onboarding_main(
            slug=slug,
            source=args.source,
            local_path=args.local_path,
            non_interactive=args.non_interactive,
            proceed_after_csv=bool(args.proceed),
            run_id=run_id,
        )
    except (ConfigError, PipelineError) as e:
        logger = get_structured_logger("tag_onboarding", run_id=run_id)
        logger.error(str(e))
        sys.exit(EXIT_CODES.get(type(e).__name__, 1))
