#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default è vietato).

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.config_utils import get_client_config, get_drive_id
from pipeline.context import ClientContext
from pipeline.drive.upload import create_drive_structure_from_names
from pipeline.exceptions import ArtifactPolicyViolation, ConfigError, PipelineError, QaGateViolation, exit_code_for
from pipeline.logging_utils import get_structured_logger, log_workflow_summary, phase_scope
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.paths import get_repo_root
from pipeline.qa_evidence import qa_evidence_path
from pipeline.qa_gate import require_qa_gate_pass
from pipeline.runtime_guard import ensure_strict_runtime
from pipeline.semantic_mapping_utils import raw_categories_from_semantic_mapping
from pipeline.tracing import start_root_trace
from pipeline.workspace_layout import WorkspaceLayout
from semantic.api import require_reviewed_vocab  # noqa: F401  # esposto per monkeypatch nei test CLI
from semantic.api import run_semantic_pipeline
from semantic.convert_service import convert_markdown  # noqa: F401  # esposto per monkeypatch nei test CLI
from semantic.embedding_service import list_content_markdown
from semantic.frontmatter_service import (  # noqa: F401  # esposto per monkeypatch nei test CLI
    enrich_frontmatter,
    write_summary_and_readme,
)
from semantic.types import SemanticContextProtocol
from storage import decision_ledger
from timmy_kb.cli.kg_builder import build_kg_for_workspace


def get_paths(slug: str) -> dict[str, Path]:
    layout = WorkspaceLayout.from_slug(slug=slug, require_drive_env=False)
    return {"base": layout.repo_root_dir, "book": layout.book_dir}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Semantic Onboarding CLI")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--no-preview", action="store_true", help="Non avviare/considerare la preview (flag nel contesto)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p.parse_args()


def _resolve_requested_effective(args: argparse.Namespace) -> tuple[dict[str, object], dict[str, object]]:
    """
    requested/effective per il gate semantic_onboarding.
    - requested = ciò che l'utente chiede via CLI
    - effective  = ciò che viene applicato davvero (qui: coincide, ma lo rendiamo esplicito)
    """
    requested = {
        "preview": "disabled" if bool(args.no_preview) else "enabled",
        "interactive": "disabled" if bool(args.non_interactive) else "enabled",
        # KG: per ora non esponiamo flag; è "auto" (dipende dall'esistenza di semantic/tags_raw.json)
        "tag_kg": "auto",
    }
    effective = dict(requested)  # in questo CLI non ci sono override/auto-correction
    return requested, effective


def _path_ref(path: Path, layout: WorkspaceLayout) -> str:
    repo_root = layout.repo_root_dir
    try:
        rel_path = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel_path = path.as_posix()
    return f"path:{rel_path}"


def _build_evidence_refs(
    *,
    layout: WorkspaceLayout,
    requested: dict[str, object],
    effective: dict[str, object],
    outcome: str,
    tag_kg_effective: str | None = None,
    exit_code: int | None = None,
) -> list[str]:
    # Se abbiamo un esito sul KG (built/skipped), lo materializziamo nell'effective
    effective_final = dict(effective)
    if tag_kg_effective is not None:
        effective_final["tag_kg"] = tag_kg_effective

    slug_value = layout.slug
    if not slug_value:
        raise ConfigError("Slug mancante nel layout durante la costruzione dell'evidence.", slug=slug_value)

    refs = [
        f"slug:{slug_value}",
        _path_ref(layout.config_path, layout),
        _path_ref(layout.semantic_dir, layout),
        f"requested:{json.dumps(requested, sort_keys=True, separators=(',', ':'))}",
        f"effective:{json.dumps(effective_final, sort_keys=True, separators=(',', ':'))}",
        f"outcome:{outcome}",
    ]

    normalized_dir = getattr(layout, "normalized_dir", None)
    if normalized_dir is not None:
        refs.append(_path_ref(normalized_dir, layout))

    if exit_code is not None:
        refs.append(f"exit_code:{int(exit_code)}")

    if tag_kg_effective is not None:
        refs.append(f"tag_kg:{tag_kg_effective}")

    return refs


def _normative_verdict_for_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION
    if isinstance(exc, QaGateViolation):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_QA_GATE_FAILED
    if isinstance(exc, ConfigError):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_CONFIG_ERROR
    if isinstance(exc, PipelineError):
        return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_PIPELINE_ERROR
    return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_UNEXPECTED_ERROR


def _deny_rationale(exc: BaseException) -> str:
    # Rationale *deterministica* (bassa entropia): non dipende dal messaggio d'errore.
    if isinstance(exc, ArtifactPolicyViolation):
        return "deny_artifact_policy_violation"
    if isinstance(exc, QaGateViolation):
        return "deny_qa_gate_failed"
    if isinstance(exc, ConfigError):
        return "deny_config_error"
    if isinstance(exc, PipelineError):
        return "deny_pipeline_error"
    return "deny_unexpected_error"


def _summarize_error(exc: BaseException) -> str:
    name = type(exc).__name__
    message = str(exc).splitlines()[:1]
    first_line = message[0] if message else "error"
    return f"{name}: {first_line}"


def _require_normalize_raw_gate(conn: Any, *, slug: str, layout: WorkspaceLayout) -> None:
    row = conn.execute(
        """
        SELECT d.decision_id, d.decided_at
        FROM decisions d
        JOIN runs r ON r.run_id = d.run_id
        WHERE r.slug = ?
          AND d.gate_name = ?
          AND d.verdict = ?
        ORDER BY d.decided_at DESC
        LIMIT 1
        """,
        (slug, "normalize_raw", decision_ledger.DECISION_ALLOW),
    ).fetchone()
    if row is not None:
        return
    raise ConfigError(
        "Gate normalize_raw mancante: esegui raw_ingest prima di semantic_onboarding.",
        slug=slug,
        file_path=layout.normalized_dir,
    )


def _qa_evidence_refs(layout: WorkspaceLayout, qa_path: Path, *, status: str) -> list[str]:
    # Evidence refs deterministici e "low entropy"
    return [_path_ref(qa_path, layout), f"qa_status:{status}"]


def _run_qa_gate_and_record(conn: Any, *, layout: WorkspaceLayout, slug: str, run_id: str) -> None:
    logs_dir = layout.logs_dir
    qa_path = qa_evidence_path(logs_dir)
    decided_at = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        result = require_qa_gate_pass(logs_dir, slug=slug)
    except QaGateViolation as exc:
        evidence_refs = _qa_evidence_refs(layout, qa_path, status="failed")
        try:
            decision_ledger.record_normative_decision(
                conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=slug,
                    gate_name="qa_gate",
                    from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=decision_ledger.NORMATIVE_BLOCK,
                    subject="qa_gate",
                    decided_at=decided_at,
                    actor="cli.semantic_onboarding",
                    evidence_refs=[*evidence_refs, *(exc.evidence_refs or [])],
                    stop_code=decision_ledger.STOP_CODE_QA_GATE_FAILED,
                    reason_code="deny_qa_gate_failed",
                ),
            )
        except Exception as ledger_exc:
            raise PipelineError(
                "Ledger write failed for gate=qa_gate",
                slug=slug,
                run_id=run_id,
                hint=_summarize_error(ledger_exc),
            ) from ledger_exc
        raise

    checks_json = json.dumps(result.checks_executed, sort_keys=True, separators=(",", ":"))
    evidence_refs = [
        _path_ref(qa_path, layout),
        "qa_status:pass",
        f"checks_executed:{checks_json}",
    ]
    decision_ledger.record_normative_decision(
        conn,
        decision_ledger.NormativeDecisionRecord(
            decision_id=uuid.uuid4().hex,
            run_id=run_id,
            slug=slug,
            gate_name="qa_gate",
            from_state=decision_ledger.STATE_SEMANTIC_INGEST,
            to_state=decision_ledger.STATE_SEMANTIC_INGEST,
            verdict=decision_ledger.NORMATIVE_PASS,
            subject="qa_gate",
            decided_at=decided_at,
            actor="cli.semantic_onboarding",
            evidence_refs=evidence_refs,
        ),
    )


def _merge_evidence_refs(base: list[str], exc: BaseException) -> list[str]:
    if isinstance(exc, (ArtifactPolicyViolation, QaGateViolation)):
        return [*base, *(exc.evidence_refs or [])]
    return base


def build_normative_failure_record(
    *,
    exc: BaseException,
    code: int,
    layout: WorkspaceLayout,
    requested: dict[str, object],
    effective: dict[str, object],
    slug: str,
    run_id: str,
    decision_id: str,
    decided_at: str,
) -> decision_ledger.NormativeDecisionRecord:
    """Costruisce il record normativo di failure senza side-effect (no I/O, no logging)."""
    if isinstance(exc, (ConfigError, PipelineError)):
        verdict, stop_code = _normative_verdict_for_error(exc)
        rationale = _deny_rationale(exc)
        evidence_refs = _merge_evidence_refs(
            _build_evidence_refs(
                layout=layout,
                requested=requested,
                effective=effective,
                outcome=rationale,
                exit_code=code,
            ),
            exc,
        )
    else:
        verdict = decision_ledger.NORMATIVE_FAIL
        stop_code = decision_ledger.STOP_CODE_UNEXPECTED_ERROR
        rationale = "deny_unexpected_error"
        evidence_refs = _build_evidence_refs(
            layout=layout,
            requested=requested,
            effective=effective,
            outcome=rationale,
            exit_code=code,
        )

    return decision_ledger.NormativeDecisionRecord(
        decision_id=decision_id,
        run_id=run_id,
        slug=slug,
        gate_name="semantic_onboarding",
        from_state=decision_ledger.STATE_SEMANTIC_INGEST,
        to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
        verdict=verdict,
        subject="semantic_onboarding",
        decided_at=decided_at,
        actor="cli.semantic_onboarding",
        evidence_refs=evidence_refs,
        stop_code=stop_code,
        reason_code=rationale,
    )


def _apply_cli_flags_to_context(ctx: SemanticContextProtocol, args: argparse.Namespace) -> None:
    """Trasferisce flag CLI puliti nel contesto senza side-effect nascosti."""
    ctx.skip_preview = bool(args.no_preview)
    ctx.no_interactive = bool(args.non_interactive)


def _log_semantic_summary(
    logger: logging.Logger,
    layout: WorkspaceLayout,
    touched: list[Path],
    slug: str,
) -> dict[str, object]:
    """
    Raccoglie e logga metadati riassuntivi.
    Policy: best-effort (NON influenza exit code / ledger / gate), ma NON è silenzioso.
    """
    book_dir: Path = layout.book_dir
    repo_root_dir = layout.repo_root_dir
    summary_path = book_dir / "SUMMARY.md"
    readme_path = book_dir / "README.md"

    summary_extra: dict[str, object] = {
        "book_dir": str(book_dir),
        "repo_root_dir": str(repo_root_dir),
        "frontmatter": len(touched),
        "summary_failed": False,
    }

    try:
        content_mds = list_content_markdown(book_dir)
        summary_extra.update(
            {
                "markdown": len(content_mds),
                "summary_exists": summary_path.exists(),
                "readme_exists": readme_path.exists(),
            }
        )
        log_workflow_summary(
            logger,
            event="cli.semantic_onboarding.summary",
            slug=slug,
            artifacts=len(content_mds),
            extra=summary_extra,
        )
    except (OSError, ValueError) as exc:
        # Evita payload ad alta entropia: tipo si, messaggio no (resta nel traceback se serve).
        logger.warning(
            "cli.semantic_onboarding.summary_failed",
            extra={
                "slug": slug,
                "stage": "semantic_summary",
                "error_type": type(exc).__name__,
            },
        )
        summary_extra.update(
            {
                "summary_failed": True,
                "summary_error_type": type(exc).__name__,
            }
        )

    return summary_extra


def _run_tag_kg_builder(ctx: SemanticContextProtocol, layout: WorkspaceLayout, logger: logging.Logger) -> str:
    """Esegue il KG builder se tags_raw.json esiste, ritorna 'built'/'skipped'."""
    semantic_dir = layout.semantic_dir
    tags_raw_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
    if tags_raw_path.exists():
        with phase_scope(logger, stage="cli.tag_kg_builder", customer=layout.slug):
            build_kg_for_workspace(ctx, namespace=layout.slug)
        return "built"
    logger.info(
        "cli.tag_kg_builder.skipped",
        extra={"slug": layout.slug, "reason": "semantic/tags_raw.json assente"},
    )
    return "skipped"


def _record_failure_and_log(
    *,
    exc: BaseException,
    code: int,
    layout: WorkspaceLayout,
    requested: dict[str, object],
    effective: dict[str, object],
    slug: str,
    run_id: str,
    ledger_conn: Any,
    logger: logging.Logger,
) -> None:
    """Registra la failure nel ledger e logga eventuali errori di persistenza."""
    original_error = _summarize_error(exc)
    record = build_normative_failure_record(
        exc=exc,
        code=code,
        layout=layout,
        requested=requested,
        effective=effective,
        slug=slug,
        run_id=run_id,
        decision_id=uuid.uuid4().hex,
        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    try:
        decision_ledger.record_normative_decision(
            ledger_conn,
            record,
        )
    except Exception as ledger_exc:
        ledger_error = _summarize_error(ledger_exc)
        logger.error(
            "cli.semantic_onboarding.ledger_write_failed",
            extra={
                "slug": slug,
                "run_id": run_id,
                "stage": "semantic_onboarding",
                "gate": "semantic_onboarding",
                "ledger_error": ledger_error,
                "original_error": original_error,
            },
        )
        raise PipelineError(
            "Ledger write failed for gate=semantic_onboarding "
            f"slug={slug} run_id={run_id} stage=semantic_onboarding; "
            f"ledger_error={ledger_error}; original_error={original_error}",
            slug=slug,
            run_id=run_id,
        ) from ledger_exc


def _run_semantic_flow(
    *,
    ctx: SemanticContextProtocol,
    layout: WorkspaceLayout,
    logger: logging.Logger,
    slug: str,
    run_id: str,
    ledger_conn: Any,
    requested: dict[str, object],
    effective: dict[str, object],
) -> tuple[int, list[Path], WorkspaceLayout]:
    """Orchestrazione pura del flusso semantic_onboarding con ledger e policy gates."""
    touched: list[Path] = []
    try:
        tag_kg_effective: str | None = None

        _require_normalize_raw_gate(ledger_conn, slug=slug, layout=layout)

        try:
            _run_qa_gate_and_record(
                ledger_conn,
                layout=layout,
                slug=slug,
                run_id=run_id,
            )
        except QaGateViolation as qa_exc:
            logger.error(
                "cli.semantic_onboarding.qa_gate_failed",
                extra={"slug": slug, "error": _summarize_error(qa_exc)},
            )
            return int(exit_code_for(qa_exc)), touched, layout

        _repo_root_dir, _mds, touched = run_semantic_pipeline(ctx, logger, slug=slug)

        enforce_core_artifacts("semantic_onboarding", layout=layout)

        cfg = get_client_config(ctx) or {}
        drive_raw_id = get_drive_id(cfg, "raw_folder_id")
        if drive_raw_id:
            # Re-load layout (tollera evoluzioni del context durante pipeline)
            layout = WorkspaceLayout.from_context(ctx)
            mapping_path = ensure_within_and_resolve(
                layout.semantic_dir,
                layout.semantic_dir / "semantic_mapping.yaml",
            )
            categories = raw_categories_from_semantic_mapping(
                semantic_dir=layout.semantic_dir,
                mapping_path=Path(mapping_path),
            )
            if not categories:
                raise ConfigError("semantic_mapping.yaml non contiene aree valide: impossibile creare raw su Drive")
            create_drive_structure_from_names(
                ctx=ctx,
                folder_names=categories,
                parent_folder_id=drive_raw_id,
                log=logger,
            )

        tag_kg_effective = _run_tag_kg_builder(ctx, layout, logger)
        if tag_kg_effective == "built":
            semantic_dir = layout.semantic_dir
            kg_json = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")
            kg_md = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")
            if kg_json.exists() and kg_md.exists():
                decision_ledger.record_normative_decision(
                    ledger_conn,
                    decision_ledger.NormativeDecisionRecord(
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                        to_state=decision_ledger.STATE_VISUALIZATION_REFRESH,
                        verdict=decision_ledger.NORMATIVE_PASS,
                        subject="tag_kg_builder",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        actor="cli.semantic_onboarding",
                        evidence_refs=_build_evidence_refs(
                            layout=layout,
                            requested=requested,
                            effective=effective,
                            outcome="ok",
                            tag_kg_effective=tag_kg_effective,
                        ),
                        reason_code="ok",
                    ),
                )
            else:
                logger.error("cli.tag_kg_builder.outputs_missing", extra={"slug": slug})
                decision_ledger.record_normative_decision(
                    ledger_conn,
                    decision_ledger.NormativeDecisionRecord(
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                        to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                        verdict=decision_ledger.NORMATIVE_BLOCK,
                        subject="tag_kg_builder",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        actor="cli.semantic_onboarding",
                        evidence_refs=[
                            _path_ref(kg_json, layout),
                            _path_ref(kg_md, layout),
                            "tag_kg:missing_outputs",
                        ],
                        stop_code=decision_ledger.STOP_CODE_PIPELINE_ERROR,
                        reason_code="deny_kg_outputs_missing",
                    ),
                )
                raise ConfigError(
                    "Tag KG builder ha prodotto output incompleti (kg.tags.json/kg.tags.md mancanti).",
                    slug=slug,
                )

        # PASS del gate semantic_onboarding SOLO a valle anche del KG (built o skipped)
        decision_ledger.record_normative_decision(
            ledger_conn,
            decision_ledger.NormativeDecisionRecord(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                slug=slug,
                gate_name="semantic_onboarding",
                from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                verdict=decision_ledger.NORMATIVE_PASS,
                subject="semantic_onboarding",
                decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                actor="cli.semantic_onboarding",
                evidence_refs=_build_evidence_refs(
                    layout=layout,
                    requested=requested,
                    effective=effective,
                    outcome="ok",
                    tag_kg_effective=tag_kg_effective,
                ),
                reason_code="ok",
            ),
        )
        return 0, touched, layout

    except (ConfigError, PipelineError) as exc:
        original_error = _summarize_error(exc)
        code: int = int(exit_code_for(exc))  # exit_code_for non è tipizzato: forza int per mypy
        _record_failure_and_log(
            exc=exc,
            code=code,
            layout=layout,
            requested=requested,
            effective=effective,
            slug=slug,
            run_id=run_id,
            ledger_conn=ledger_conn,
            logger=logger,
        )

        logger.error(
            "cli.semantic_onboarding.failed",
            extra={"slug": slug, "error": original_error},
        )
        return code, touched, layout

    except Exception as exc:
        code = 99
        _record_failure_and_log(
            exc=exc,
            code=code,
            layout=layout,
            requested=requested,
            effective=effective,
            slug=slug,
            run_id=run_id,
            ledger_conn=ledger_conn,
            logger=logger,
        )

        logger.exception(
            "cli.semantic_onboarding.unexpected_error",
            extra={"slug": slug, "error_type": type(exc).__name__},
        )
        return code, touched, layout


def main() -> int:
    # Parse args FIRST: evita side-effects (log/init) quando l'utente chiede solo --help.
    args = _parse_args()
    slug: str = args.slug.strip()
    if not slug:
        raise ConfigError("Slug vuoto non valido per semantic_onboarding.")

    # ENTRYPOINT STRICT (no bootstrap): la CLI risolve la repo root per il perimetro,
    # ma NON crea/rigenera config/struttura. Prerequisito: workspace già configurato.
    # (dopo argparse, così --help resta quiet)
    ensure_strict_runtime(context="cli.semantic_onboarding")
    get_repo_root()

    run_id = uuid.uuid4().hex
    settings = get_observability_settings()
    logger = get_structured_logger(
        "semantic.onboarding",
        run_id=run_id,
        level=settings.log_level,
        redact_logs=settings.redact_logs,
        enable_tracing=settings.tracing_enabled,
    )

    # Inizializza per sicurezza (evita UnboundLocalError nel riepilogo)
    touched: list[Path] = []

    # Carica contesto locale (niente Drive / env obbligatori)
    ctx: SemanticContextProtocol = ClientContext.load(
        slug=slug,
        require_drive_env=False,
        run_id=run_id,
        bootstrap_config=False,
    )
    layout = WorkspaceLayout.from_context(ctx)
    requested, effective = _resolve_requested_effective(args)

    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(
        ledger_conn,
        run_id=run_id,
        slug=slug,
        started_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    try:
        _apply_cli_flags_to_context(ctx, args)

        env = os.getenv("TIMMY_ENV", "dev")
        logger.info("cli.semantic_onboarding.started", extra={"slug": slug})

        with start_root_trace(
            "onboarding",
            slug=slug,
            run_id=run_id,
            entry_point="cli",
            env=env,
            trace_kind="onboarding",
        ):

            exit_code, touched, layout = _run_semantic_flow(
                ctx=ctx,
                layout=layout,
                logger=logger,
                slug=slug,
                run_id=run_id,
                ledger_conn=ledger_conn,
                requested=requested,
                effective=effective,
            )
            if exit_code != 0:
                return exit_code

        # Riepilogo artefatti: best-effort (non influenza artefatti/gate/ledger/exit code) ma non silenzioso.
        summary_extra = _log_semantic_summary(logger, layout, touched, slug)
        logger.info(
            "cli.semantic_onboarding.completed",
            extra={"slug": slug, "artifacts": int(len(touched)), **summary_extra},
        )
        return 0

    finally:
        ledger_conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
