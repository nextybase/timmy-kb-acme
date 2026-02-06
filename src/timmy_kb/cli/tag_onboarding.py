#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# SPDX-License-Identifier: GPL-3.0-or-later

# src/tag_onboarding.py

"""

Orchestratore: Tag Onboarding (HiTL)



Step intermedio tra `raw_ingest` e `semantic_onboarding`.

A partire dai file normalizzati in `normalized/`, produce un CSV con i tag suggeriti e

(dopo conferma) genera gli stub per la revisione semantica.



Punti chiave:

- Niente `print()` → logging strutturato.

- Path-safety STRONG con `ensure_within`.

- Scritture atomiche centralizzate con `safe_write_text`.

- Nessuna ingestione: la fase di acquisizione/normalizzazione e' separata.

- Checkpoint HiTL tra CSV e generazione stub semantici.

"""


from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional, cast

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.beta_flags import is_beta_strict
from pipeline.cli_runner import run_cli_orchestrator
from pipeline.context import ClientContext
from pipeline.exceptions import ArtifactPolicyViolation, ConfigError, PathTraversalError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger, tail_path
from pipeline.metrics import start_metrics_server_once
from pipeline.normalized_index import validate_index as validate_normalized_index
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import (  # STRONG guard SSoT
    ensure_valid_slug,
    ensure_within,
    ensure_within_and_resolve,
    iter_safe_paths,
    open_for_read_bytes_selfguard,
)
from pipeline.runtime_guard import ensure_strict_runtime
from pipeline.tracing import start_root_trace
from pipeline.types import TaggingPayload
from pipeline.workspace_layout import WorkspaceLayout
from semantic import nlp_runner
from semantic.tags_validator import validate_tags_reviewed as validate_tags_payload
from semantic.tags_validator import write_validation_report as write_validation_report_payload
from semantic.types import ClientContextProtocol
from storage import decision_ledger
from storage.tags_store import clear_doc_terms, derive_db_path_from_yaml_path, ensure_schema_v2, get_conn, has_doc_terms
from storage.tags_store import load_tags_reviewed as load_tags_reviewed_db
from storage.tags_store import upsert_document, upsert_folder

from .tag_onboarding_context import ContextResources, prepare_context
from .tag_onboarding_semantic import emit_csv_phase, emit_stub_phase

_DUMMY_TRUTHY = {"1", "true", "yes", "on"}


def _prompt(msg: str) -> str:
    """Raccoglie input testuale da CLI (abilitato **solo** negli orchestratori)."""

    return input(msg).strip()


def _obs_kwargs() -> dict[str, Any]:
    settings = get_observability_settings()
    return {
        "level": settings.log_level,
        "redact_logs": settings.redact_logs,
        "enable_tracing": settings.tracing_enabled,
    }


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summarize_error(exc: BaseException) -> str:
    name = type(exc).__name__
    message = str(exc).splitlines()[:1]
    first_line = message[0] if message else "error"
    return f"{name}: {first_line}"


def _is_dummy_allowed() -> bool:
    # Capability-gate: dummy ammesso solo in ambienti esplicitamente abilitati (dev/demo/tooling)
    v = os.getenv("TIMMY_ALLOW_DUMMY", "")
    return v.strip().lower() in _DUMMY_TRUTHY


def _build_evidence_refs(
    layout: WorkspaceLayout,
    *,
    dummy_mode: bool,
    requested_mode: str,
    strict_mode: bool,
    effective_mode: str,
) -> list[str]:
    slug_value = layout.slug
    if not slug_value:
        raise ConfigError("Slug mancante nel layout durante la costruzione dell'evidence.", slug=slug_value)
    return [
        f"slug:{slug_value}",
        _path_ref(layout.config_path, layout),
        _path_ref(layout.normalized_dir, layout),
        _path_ref(layout.semantic_dir, layout),
        f"dummy_mode:{str(bool(dummy_mode)).lower()}",
        f"requested_mode:{requested_mode}",
        f"strict_mode:{str(bool(strict_mode)).lower()}",
        f"effective_mode:{effective_mode}",
        "force_dummy:false",
        "gate_scope:intra_state",
        "state_transition:false",
    ]


def _path_ref(path: Path, layout: WorkspaceLayout) -> str:
    try:
        repo_root = layout.repo_root_dir
        rel_path = path.relative_to(repo_root).as_posix() if repo_root else path.as_posix()
    except Exception:
        rel_path = path.as_posix()
    return f"path:{rel_path}"


def _normative_verdict_for_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION
    if isinstance(exc, ConfigError):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_CONFIG_ERROR
    if isinstance(exc, PipelineError):
        return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_PIPELINE_ERROR
    return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_UNEXPECTED_ERROR


def _deny_rationale(exc: BaseException) -> str:
    if isinstance(exc, ArtifactPolicyViolation):
        return "deny_artifact_policy_violation"
    if isinstance(exc, ConfigError):
        return "deny_config_error"
    if isinstance(exc, PipelineError):
        return "deny_pipeline_error"
    return "deny_unexpected_error"


def _resolve_modes(*, dummy_mode: bool, strict_mode: bool) -> tuple[str, str, str]:
    requested_mode = "dummy" if dummy_mode else "standard"
    if dummy_mode and strict_mode:
        effective_mode = "strict"
        rationale = "dummy_blocked_by_strict"
    elif dummy_mode:
        effective_mode = "dummy"
        rationale = "dummy_allowed"
    else:
        effective_mode = "standard"
        rationale = "checkpoint_proceeded_no_stub"
    return requested_mode, effective_mode, rationale


def _require_normalized_index(layout: WorkspaceLayout, *, normalized_dir: Path) -> None:
    index_path = ensure_within_and_resolve(normalized_dir, normalized_dir / "INDEX.json")
    validate_normalized_index(
        repo_root_dir=layout.repo_root_dir,
        normalized_dir=normalized_dir,
        index_path=index_path,
    )


# ───────────────────────────── Core: ingest locale ───────────────────────────────────


def compute_sha256(path: Path) -> str:
    """SHA-256 streaming del file (chunk 8 KiB) con guardie di lettura sicure."""

    h = hashlib.sha256()

    with open_for_read_bytes_selfguard(path) as f:

        for chunk in iter(lambda: f.read(8192), b""):

            h.update(chunk)

    return h.hexdigest()


def upsert_folder_chain(conn: Any, normalized_dir: Path, folder_path: Path) -> int:
    """Crea (se mancano) tutte le cartelle da 'normalized' fino a `folder_path`.



    Ritorna l'ID della cartella terminale.

    """

    # Normalizza e verifica che folder_path sia sotto normalized_dir (guard forte)

    normalized_dir = Path(normalized_dir).resolve()

    folder_path = Path(folder_path).resolve()

    ensure_within(normalized_dir, folder_path)

    rel = folder_path.relative_to(normalized_dir)

    # Inserisci/aggiorna la root logica 'normalized'

    parent_id: Optional[int] = upsert_folder(conn, "normalized", None)

    current_db_path = "normalized"

    # Crea la catena discendente: normalized/part1[/part2...]

    for part in rel.parts:

        current_db_path = f"{current_db_path}/{part}".replace("\\", "/")

        parent_db_path = str(Path(current_db_path).parent).replace("\\", "/")

        if parent_db_path == ".":

            parent_db_path = "normalized"

        parent_id = upsert_folder(conn, current_db_path, parent_db_path)

    if parent_id is None:

        raise PipelineError("upsert_folder_chain: parent_id non determinato", file_path=str(folder_path))

    return parent_id


def scan_normalized_to_db(
    normalized_dir: str | Path,
    db_path: str | Path,
    *,
    repo_root_dir: Path | None = None,
) -> dict[str, int]:
    """Indicizza cartelle e markdown di `normalized/` dentro il DB (schema v2)."""

    if is_beta_strict() and repo_root_dir is None:
        raise ConfigError(
            "repo_root_dir mancante: richiesto in strict mode per scan_normalized_to_db.",
        )
    # Fallback is CLI/tooling only; avoid heuristics, prefer ClientContext/WorkspaceLayout when available.
    repo_root_dir_path = (
        Path(repo_root_dir).resolve() if repo_root_dir is not None else Path(normalized_dir).resolve().parent
    )
    perimeter_root = repo_root_dir_path

    normalized_dir_path = ensure_within_and_resolve(perimeter_root, normalized_dir)

    db_path_path = ensure_within_and_resolve(perimeter_root, db_path)

    ensure_schema_v2(str(db_path_path))

    folders_count = 0

    docs_count = 0

    log = get_structured_logger("tag_onboarding", **_obs_kwargs())

    with get_conn(str(db_path_path)) as conn:

        # registra root 'normalized'

        upsert_folder(conn, "normalized", None)

        for path in iter_safe_paths(normalized_dir_path, include_dirs=True, include_files=True):

            if path.is_dir():

                upsert_folder_chain(conn, normalized_dir_path, path)

                folders_count += 1

                continue

            if path.is_file() and path.suffix.lower() == ".md":

                folder_id = upsert_folder_chain(conn, normalized_dir_path, path.parent)

                sha256_new = compute_sha256(path)

                pages = None

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
    normalized_dir: Path | str,
    db_path: str | Path,
    *,
    repo_root_dir: Path | None = None,
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

    strict_mode = is_beta_strict()
    if strict_mode and repo_root_dir is None:
        raise ConfigError(
            "repo_root_dir mancante: richiesto in strict mode per run_nlp_to_db.",
            slug=slug,
        )
    # Fallback is CLI/tooling only; avoid heuristics, prefer ClientContext/WorkspaceLayout when available.
    repo_root_dir_path = (
        Path(repo_root_dir).resolve() if repo_root_dir is not None else Path(normalized_dir).resolve().parent
    )
    perimeter_root = repo_root_dir_path

    normalized_dir_path = ensure_within_and_resolve(perimeter_root, normalized_dir)

    db_path_path = ensure_within_and_resolve(perimeter_root, db_path)

    ensure_schema_v2(str(db_path_path))

    log = get_structured_logger("tag_onboarding", **_obs_kwargs())

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
            normalized_dir_path=normalized_dir_path,
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

    entities_status: str | None = None
    if enable_entities:
        try:
            entities_module = importlib.import_module("semantic.entities_runner")
            run_doc_entities_pipeline = getattr(entities_module, "run_doc_entities_pipeline")
        except Exception as exc:
            log.error(
                "tag_onboarding.entities.failed",
                extra={"slug": slug, "error_type": type(exc).__name__, "strict": strict_mode},
            )
            raise PipelineError(
                "Entities pipeline non disponibile.",
                slug=slug,
                file_path=str(db_path_path),
            ) from exc
        try:
            # repo_root_dir here is workspace root, not the system REPO_ROOT_DIR.
            ent_stats = run_doc_entities_pipeline(
                repo_root_dir=repo_root_dir_path,
                raw_dir=normalized_dir_path,
                semantic_dir=repo_root_dir_path / "semantic",
                db_path=db_path_path,
                slug=slug,
                logger=log,
            )
            stats = {**stats, **ent_stats}
            entities_status = "ok"
        except Exception as exc:  # pragma: no cover
            log.error(
                "tag_onboarding.entities.failed",
                extra={"slug": slug, "error_type": type(exc).__name__, "strict": strict_mode},
            )
            raise PipelineError(
                "Entities pipeline fallita.",
                slug=slug,
                file_path=str(db_path_path),
            ) from exc

    enriched_stats = {
        **stats,
        "workers": worker_count,
        "batch_size": worker_batch_size,
    }
    if entities_status is not None:
        enriched_stats["entities_status"] = entities_status

    log.info("cli.tag_onboarding.nlp_completed", extra=enriched_stats)

    return enriched_stats


def validate_tags_reviewed(slug: str, run_id: Optional[str] = None) -> int:
    """Valida `semantic/tags_reviewed.yaml` sfruttando il contesto cliente."""

    context = ClientContext.load(
        slug=slug,
        require_drive_env=False,
        run_id=run_id,
        stage="validate",
        bootstrap_config=False,
    )
    layout = _require_layout(context)
    repo_root_dir = layout.repo_root_dir
    semantic_candidate = layout.semantic_dir
    try:
        semantic_dir = ensure_within_and_resolve(repo_root_dir, semantic_candidate)
    except PathTraversalError:
        logs_dir = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = ensure_within_and_resolve(logs_dir, logs_dir / "tag_onboarding_validate.log")
        logger = get_structured_logger(
            "tag_onboarding.validate",
            log_file=log_file,
            context=context,
            run_id=run_id,
            **_obs_kwargs(),
        )
        logger.error(
            "cli.tag_onboarding.semantic_outside_base",
            extra={"semantic_dir": str(semantic_candidate)},
        )
        return 1

    yaml_candidate = semantic_dir / "tags_reviewed.yaml"
    yaml_path = ensure_within_and_resolve(semantic_dir, yaml_candidate)
    report_candidate = semantic_dir / "tags_review_validation.json"
    report_path = ensure_within_and_resolve(semantic_dir, report_candidate)

    db_candidate = Path(derive_db_path_from_yaml_path(yaml_path))
    db_path = ensure_within_and_resolve(repo_root_dir, db_candidate)

    logs_dir = ensure_within_and_resolve(repo_root_dir, repo_root_dir / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = ensure_within_and_resolve(logs_dir, logs_dir / "tag_onboarding_validate.log")

    logger = get_structured_logger(
        "tag_onboarding.validate",
        log_file=log_file,
        context=context,
        run_id=run_id,
        **_obs_kwargs(),
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

        logger.error("cli.tag_onboarding.validation_error", extra={"error": str(e)})

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

            logger.info("cli.tag_onboarding.stop_after_csv", extra={"reason": "non_interactive"})

            return False

        return True

    cont = _prompt(
        "Controlla e approva i tag generati. " "Sei pronto per proseguire con l'arricchimento semantico? (y/n): "
    ).lower()

    if cont != "y":

        logger.info("cli.tag_onboarding.user_aborted", extra={"choice": cont})

        return False

    return True


def _require_layout(context: ClientContextProtocol | ClientContext) -> WorkspaceLayout:
    if getattr(context, "repo_root_dir", None) is None:
        raise ConfigError(
            "Contesto privo di repo_root_dir: impossibile risolvere il workspace in modo deterministico.",
            slug=getattr(context, "slug", None),
        )
    return WorkspaceLayout.from_context(cast(Any, context))


def _merge_evidence_refs(base: list[str], exc: BaseException) -> list[str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return [*base, *exc.evidence_refs]
    return base


def tag_onboarding_main(
    slug: str,
    *,
    non_interactive: bool = False,
    proceed_after_csv: bool = False,
    dummy_mode: bool = False,
    run_id: Optional[str] = None,
) -> None:
    """Orchestratore della fase di *Tag Onboarding*."""

    run_id = run_id or uuid.uuid4().hex
    early_logger = get_structured_logger("tag_onboarding", run_id=run_id, **_obs_kwargs())

    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # Context + logger coerenti con orchestratori

    context_preparer = prepare_context
    resources: ContextResources = context_preparer(
        slug=slug,
        non_interactive=non_interactive,
        run_id=run_id,
        require_drive_env=False,
    )

    context = resources.context
    layout = _require_layout(context)
    ledger_conn = None
    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(
        ledger_conn,
        run_id=run_id,
        slug=slug,
        started_at=_utc_now_iso(),
    )
    dummy_mode = bool(dummy_mode)
    strict_mode_resolved = is_beta_strict()
    requested_mode = "dummy" if dummy_mode else "standard"
    decision_recorded = False
    if dummy_mode and not strict_mode_resolved and not _is_dummy_allowed():
        evidence_refs = _build_evidence_refs(
            layout,
            dummy_mode=True,
            requested_mode="dummy",
            strict_mode=False,
            effective_mode="forbidden",
        )
        decision_ledger.record_normative_decision(
            ledger_conn,
            decision_ledger.NormativeDecisionRecord(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                slug=slug,
                gate_name="tag_onboarding",
                from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                verdict=decision_ledger.NORMATIVE_BLOCK,
                subject="tag_onboarding",
                decided_at=_utc_now_iso(),
                actor="cli.tag_onboarding",
                evidence_refs=evidence_refs,
                stop_code=decision_ledger.STOP_CODE_CAPABILITY_DUMMY_FORBIDDEN,
                reason_code="deny_dummy_capability_forbidden",
            ),
        )
        decision_recorded = True
        raise ConfigError(
            "Dummy mode non consentita: abilita TIMMY_ALLOW_DUMMY=1 (solo dev/demo/tooling).",
            slug=slug,
        )

    requested_mode, effective_mode, effective_rationale = _resolve_modes(
        dummy_mode=dummy_mode,
        strict_mode=strict_mode_resolved,
    )
    evidence_refs = _build_evidence_refs(
        layout,
        dummy_mode=dummy_mode,
        requested_mode=requested_mode,
        strict_mode=strict_mode_resolved,
        effective_mode=effective_mode,
    )

    payload: TaggingPayload = {
        "workspace_slug": slug,
        "normalized_dir": resources.normalized_dir,
        "semantic_dir": resources.semantic_dir,
        "run_id": run_id,
        "extra": {"proceed_after_csv": bool(proceed_after_csv)},
    }

    normalized_dir = payload["normalized_dir"]

    semantic_dir = payload["semantic_dir"]

    logger = resources.logger

    logger.info(
        "cli.tag_onboarding.started",
        extra={"slug": payload["workspace_slug"]},
    )
    current_stage = "normalized_check"

    # Sorgente di PDF

    try:
        _require_normalized_index(layout, normalized_dir=normalized_dir)

        current_stage = "csv_phase"
        csv_path = emit_csv_phase(context, logger, slug=slug, semantic_dir=semantic_dir)
        enforce_core_artifacts("tag_onboarding", layout=layout, stub_expected=False)

        current_stage = "checkpoint"
        if not _should_proceed(non_interactive=non_interactive, proceed_after_csv=proceed_after_csv, logger=logger):
            decision_ledger.record_normative_decision(
                ledger_conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=slug,
                    gate_name="tag_onboarding",
                    from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=decision_ledger.NORMATIVE_PASS,
                    subject="tag_onboarding",
                    decided_at=_utc_now_iso(),
                    actor="cli.tag_onboarding",
                    evidence_refs=evidence_refs,
                    reason_code="ok",
                ),
            )
            return

        if effective_mode != "dummy":
            decision_ledger.record_normative_decision(
                ledger_conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=slug,
                    gate_name="tag_onboarding",
                    from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=decision_ledger.NORMATIVE_PASS,
                    subject="tag_onboarding",
                    decided_at=_utc_now_iso(),
                    actor="cli.tag_onboarding",
                    evidence_refs=evidence_refs,
                    reason_code=effective_rationale,
                ),
            )
            return

        current_stage = "stub_phase"
        emit_stub_phase(semantic_dir, csv_path, logger, context=context)
        enforce_core_artifacts("tag_onboarding", layout=layout, stub_expected=True)
        proceed_after_csv_flag = bool(payload["extra"]["proceed_after_csv"]) if payload["extra"] else False
        logger.info(
            "cli.tag_onboarding.completed",
            extra={
                "slug": payload["workspace_slug"],
                "proceed_after_csv": proceed_after_csv_flag,
            },
        )
        decision_ledger.record_normative_decision(
            ledger_conn,
            decision_ledger.NormativeDecisionRecord(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                slug=slug,
                gate_name="tag_onboarding",
                from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                verdict=decision_ledger.NORMATIVE_PASS,
                subject="tag_onboarding",
                decided_at=_utc_now_iso(),
                actor="cli.tag_onboarding",
                evidence_refs=evidence_refs,
                reason_code="ok_dummy_mode",
            ),
        )
    except Exception as exc:
        if decision_recorded:
            raise
        original_error = _summarize_error(exc)
        try:
            verdict, stop_code = _normative_verdict_for_error(exc)
            decision_ledger.record_normative_decision(
                ledger_conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=slug,
                    gate_name="tag_onboarding",
                    from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=verdict,
                    subject="tag_onboarding",
                    decided_at=_utc_now_iso(),
                    actor="cli.tag_onboarding",
                    evidence_refs=_merge_evidence_refs(evidence_refs, exc),
                    stop_code=stop_code,
                    reason_code=_deny_rationale(exc),
                ),
            )
        except Exception as ledger_exc:
            ledger_error = _summarize_error(ledger_exc)
            logger.error(
                "cli.tag_onboarding.ledger_write_failed",
                extra={
                    "slug": slug,
                    "run_id": run_id,
                    "stage": current_stage,
                    "gate": "tag_onboarding",
                    "ledger_error": ledger_error,
                    "original_error": original_error,
                },
            )
            raise PipelineError(
                "Ledger write failed for gate=tag_onboarding "
                f"slug={slug} run_id={run_id} stage={current_stage}; "
                f"ledger_error={ledger_error}; original_error={original_error}",
                slug=slug,
                run_id=run_id,
            ) from ledger_exc
        raise
    finally:
        if ledger_conn is not None:
            ledger_conn.close()


# ───────────────────────────── CLI ──────────────────────────────────────────────────────────────


def _resolve_cli_paths(
    context: ClientContextProtocol | ClientContext,
    *,
    normalized_override: str | None,
    db_override: str | None,
) -> tuple[Path, Path, Path, Path]:
    """Calcola i percorsi CLI garantendo path-safety rispetto al contesto cliente."""

    layout = _require_layout(context)
    repo_root_dir = layout.repo_root_dir
    perimeter_root = repo_root_dir
    normalized_candidate = Path(normalized_override) if normalized_override else layout.normalized_dir
    normalized_dir = ensure_within_and_resolve(perimeter_root, normalized_candidate)
    semantic_dir = ensure_within_and_resolve(perimeter_root, layout.semantic_dir)

    db_candidate = Path(db_override) if db_override else (semantic_dir / "tags.db")
    db_path = ensure_within_and_resolve(perimeter_root, db_candidate)

    return repo_root_dir, normalized_dir, db_path, semantic_dir


def _parse_args() -> argparse.Namespace:
    """Costruisce e restituisce il parser CLI per `tag_onboarding`."""

    p = argparse.ArgumentParser(description=("Tag onboarding (copertura PDF + CSV + checkpoint HiTL + stub semantico)"))

    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")

    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")

    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")

    p.add_argument(
        "--proceed",
        action="store_true",
        help="In non-interattivo: prosegue anche alla fase 2 (stub semantico)",
    )
    p.add_argument(
        "--dummy",
        action="store_true",
        help="Abilita la modalita dummy end-to-end (consente la generazione degli stub).",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Esegue solo la validazione di tags_reviewed.yaml",
    )

    # Scansione NORMALIZED -> DB (opzionale)

    p.add_argument(
        "--scan-normalized",
        action="store_true",
        help="Indicizza cartelle e Markdown di normalized/ nel DB",
    )

    p.add_argument("--normalized-dir", type=str, help="Percorso della cartella normalized/")

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


def main(args: argparse.Namespace) -> int | None:
    """Entrypoint CLI orchestrato via `run_cli_orchestrator`."""
    ensure_strict_runtime(context="cli.tag_onboarding")
    run_id = uuid.uuid4().hex
    start_metrics_server_once()
    early_logger = get_structured_logger("tag_onboarding", run_id=run_id, **_obs_kwargs())

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("cli.tag_onboarding.missing_slug", extra={"slug": None})
        raise ConfigError("Missing slug in non-interactive mode")

    slug = ensure_valid_slug(
        unresolved_slug,
        interactive=not args.non_interactive,
        prompt=_prompt,
        logger=early_logger,
    )

    env = os.getenv("TIMMY_ENV", "dev")
    with start_root_trace(
        "onboarding",
        slug=slug,
        run_id=run_id,
        entry_point="cli",
        env=env,
        trace_kind="onboarding",
    ):
        if args.validate_only:
            return validate_tags_reviewed(slug, run_id=run_id)

        if getattr(args, "scan_normalized", False):
            ctx = ClientContext.load(
                slug=slug,
                require_drive_env=False,
                run_id=run_id,
                stage="scan_normalized",
                bootstrap_config=False,
            )
            repo_root_dir, normalized_dir, db_path, _ = _resolve_cli_paths(
                ctx,
                normalized_override=args.normalized_dir,
                db_override=args.db,
            )
            stats = scan_normalized_to_db(normalized_dir, db_path, repo_root_dir=repo_root_dir)
            log = get_structured_logger("tag_onboarding", run_id=run_id, context=ctx, **_obs_kwargs())
            log.info("cli.tag_onboarding.scan_completed", extra=stats)
            return 0

        if getattr(args, "nlp", False):
            ctx = ClientContext.load(
                slug=slug,
                require_drive_env=False,
                run_id=run_id,
                stage="nlp",
                bootstrap_config=False,
            )
            repo_root_dir, normalized_dir, db_path, _ = _resolve_cli_paths(
                ctx,
                normalized_override=args.normalized_dir,
                db_override=args.db,
            )
            lang = args.lang if args.lang != "auto" else "it"
            worker_override = 1 if args.nlp_no_parallel else args.nlp_workers
            stats = run_nlp_to_db(
                slug,
                normalized_dir,
                db_path,
                repo_root_dir=repo_root_dir,
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
            log = get_structured_logger("tag_onboarding", run_id=run_id, context=ctx, **_obs_kwargs())
            log.info("cli.tag_onboarding.nlp_completed", extra=stats)
            return 0

        try:
            tag_onboarding_main(
                slug=slug,
                non_interactive=args.non_interactive,
                proceed_after_csv=bool(args.proceed),
                dummy_mode=bool(args.dummy),
                run_id=run_id,
            )
            return 0
        except KeyboardInterrupt:
            raise
        except PipelineError as exc:
            logger = get_structured_logger("tag_onboarding", run_id=run_id, **_obs_kwargs())
            logger.error(
                "cli.tag_onboarding.failed",
                extra={"slug": slug, "error": str(exc), "exit_code": exit_code_for(exc)},
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger = get_structured_logger("tag_onboarding", run_id=run_id, **_obs_kwargs())
            logger.error(
                "cli.tag_onboarding.failed",
                extra={"slug": slug, "error": str(exc), "exit_code": exit_code_for(PipelineError(str(exc)))},
            )
            raise PipelineError(str(exc)) from exc


if __name__ == "__main__":

    """Entrypoint CLI orchestratore `tag_onboarding`."""

    run_cli_orchestrator("tag_onboarding", _parse_args, main)


# Sezione helper duplicati rimossa (copy/CSV delegati)
