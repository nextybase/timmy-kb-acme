#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
#
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import uuid
from pathlib import Path
from typing import TypeVar

from pipeline.paths import get_repo_root

_T = TypeVar("_T")


from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger, log_workflow_summary, phase_scope
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.tracing import start_root_trace
from pipeline.workspace_layout import WorkspaceLayout, workspace_validation_policy
from semantic.api import require_reviewed_vocab  # noqa: F401  # esposto per monkeypatch nei test CLI
from semantic.api import run_semantic_pipeline
from semantic.convert_service import convert_markdown  # noqa: F401  # esposto per monkeypatch nei test CLI
from semantic.embedding_service import list_content_markdown  # <-- PR2: import dell'helper
from semantic.frontmatter_service import (  # noqa: F401  # esposto per monkeypatch nei test CLI
    enrich_frontmatter,
    write_summary_and_readme,
)
from semantic.types import SemanticContextProtocol
from storage import decision_ledger
from timmy_kb.cli.kg_builder import build_kg_for_workspace
from timmy_kb.versioning import build_env_fingerprint


def get_paths(slug: str) -> dict[str, Path]:
    layout = WorkspaceLayout.from_slug(slug=slug, require_env=False)
    return {"base": layout.base_dir, "book": layout.book_dir}


def _default_parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Semantic Onboarding CLI")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--no-preview", action="store_true", help="Non avviare/considerare la preview (flag nel contesto)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p.parse_args()


def _parse_args() -> argparse.Namespace:
    return _default_parse_args()


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


def _build_evidence_json(
    *,
    layout: WorkspaceLayout,
    requested: dict[str, object],
    effective: dict[str, object],
    outcome: str,
    tag_kg_effective: str | None = None,
    exit_code: int | None = None,
    error_summary: str | None = None,
) -> str:
    # Se abbiamo un esito sul KG (built/skipped), lo materializziamo nell'effective
    effective_final = dict(effective)
    if tag_kg_effective is not None:
        effective_final["tag_kg"] = tag_kg_effective

    payload: dict[str, object] = {
        "slug": layout.slug,
        "workspace_root": str(layout.base_dir),
        "config_path": str(layout.config_path),
        "semantic_dir": str(layout.semantic_dir),
        "requested": requested,
        "effective": effective_final,
        "outcome": outcome,  # ok | deny_config | deny_pipeline | deny_unexpected
        # Policy: Environment Certification (best-effort evidence)
        "timmy_env": os.getenv("TIMMY_ENV", "dev"),
        "timmy_beta_strict_env": os.getenv("TIMMY_BETA_STRICT"),
        "env_fingerprint": build_env_fingerprint(),
    }
    if exit_code is not None:
        payload["exit_code"] = int(exit_code)
    if error_summary:
        payload["error"] = error_summary

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _deny_rationale(exc: BaseException) -> str:
    # Rationale *deterministica* (bassa entropia): non dipende dal messaggio d'errore.
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


def main() -> int:
    # ENTRYPOINT BOOTSTRAP - consentito: CLI standalone usa la repo root per il workspace.
    get_repo_root()
    args = _parse_args()
    slug: str = args.slug.strip()
    if not slug:
        raise ConfigError("Slug vuoto non valido per semantic_onboarding.")
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
        require_env=False,
        run_id=run_id,
        bootstrap_config=True,
    )
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(ctx)
    requested, effective = _resolve_requested_effective(args)
    ledger_conn = None
    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(
        ledger_conn,
        run_id=run_id,
        slug=slug,
        started_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    try:
        # Imposta flag UX nel contesto (contratto esplicito del semantic context)
        ctx.skip_preview = bool(args.no_preview)
        ctx.no_interactive = bool(args.non_interactive)

        env = os.getenv("TIMMY_ENV", "dev")
        overall_slug = slug
        logger.info("cli.semantic_onboarding.started", extra={"slug": slug})
        with start_root_trace(
            "onboarding",
            slug=overall_slug,
            run_id=run_id,
            entry_point="cli",
            env=env,
            trace_kind="onboarding",
        ):
            try:
                tag_kg_effective: str | None = None

                base_dir, _mds, touched = run_semantic_pipeline(
                    ctx,
                    logger,
                    slug=slug,
                )
                decision_ledger.record_decision(
                    ledger_conn,
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=slug,
                    gate_name="semantic_onboarding",
                    from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                    verdict=decision_ledger.DECISION_ALLOW,
                    subject="semantic_onboarding",
                    decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    evidence_json=_build_evidence_json(
                        layout=layout,
                        requested=requested,
                        effective=effective,
                        outcome="ok",
                    ),
                    rationale="ok",
                )

                # 3) Costruisci il Knowledge Graph dei tag (Tag KG Builder)
                semantic_dir = layout.semantic_dir
                # Path-safety: blocca traversal/symlink fuori semantic_dir.
                tags_raw_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
                if tags_raw_path.exists():
                    with phase_scope(logger, stage="cli.tag_kg_builder", customer=slug):
                        build_kg_for_workspace(base_dir, namespace=slug)
                    tag_kg_effective = "built"
                else:
                    logger.info(
                        "cli.tag_kg_builder.skipped",
                        extra={"slug": slug, "reason": "semantic/tags_raw.json assente"},
                    )
                    tag_kg_effective = "skipped"
                if tag_kg_effective == "built":
                    kg_json = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.json")
                    kg_md = ensure_within_and_resolve(semantic_dir, semantic_dir / "kg.tags.md")
                    if kg_json.exists() and kg_md.exists():
                        decision_ledger.record_decision(
                            ledger_conn,
                            decision_id=uuid.uuid4().hex,
                            run_id=run_id,
                            slug=slug,
                            gate_name="semantic_onboarding",
                            from_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                            to_state=decision_ledger.STATE_VISUALIZATION_REFRESH,
                            verdict=decision_ledger.DECISION_ALLOW,
                            subject="tag_kg_builder",
                            decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            evidence_json=_build_evidence_json(
                                layout=layout,
                                requested=requested,
                                effective=effective,
                                outcome="ok",
                                tag_kg_effective=tag_kg_effective,
                            ),
                            rationale="ok",
                        )
            except (ConfigError, PipelineError) as exc:
                # Mappa verso exit code deterministici (no traceback non gestiti)
                original_error = _summarize_error(exc)
                code: int = int(exit_code_for(exc))  # exit_code_for non è tipizzato: forza int per mypy
                try:
                    decision_ledger.record_decision(
                        ledger_conn,
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                        to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                        verdict=decision_ledger.DECISION_DENY,
                        subject="semantic_onboarding",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        evidence_json=_build_evidence_json(
                            layout=layout,
                            requested=requested,
                            effective=effective,
                            outcome=_deny_rationale(exc),
                            exit_code=code,
                            error_summary=original_error,
                        ),
                        rationale=_deny_rationale(exc),
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
                logger.error("cli.semantic_onboarding.failed", extra={"slug": slug, "error": str(exc)})
                return code
            except Exception as exc:
                original_error = _summarize_error(exc)
                code = 99
                try:
                    decision_ledger.record_decision(
                        ledger_conn,
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state=decision_ledger.STATE_SEMANTIC_INGEST,
                        to_state=decision_ledger.STATE_FRONTMATTER_ENRICH,
                        verdict=decision_ledger.DECISION_DENY,
                        subject="semantic_onboarding",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        evidence_json=_build_evidence_json(
                            layout=layout,
                            requested=requested,
                            effective=effective,
                            outcome="deny_unexpected_error",
                            exit_code=code,
                            error_summary=original_error,
                        ),
                        rationale="deny_unexpected_error",
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
                logger.exception("cli.semantic_onboarding.unexpected_error", extra={"slug": slug, "error": str(exc)})
                return code

        # Riepilogo artefatti (best-effort, non influenza l'exit code)
        summary_extra: dict[str, object] = {}
        try:
            book_dir: Path = layout.book_dir
            summary_path = book_dir / "SUMMARY.md"
            readme_path = book_dir / "README.md"

            content_mds = list_content_markdown(book_dir)
            summary_extra = {
                "book_dir": str(book_dir),
                "base_dir": str(layout.base_dir),
                "markdown": len(content_mds),
                "frontmatter": len(touched),
                "summary_exists": summary_path.exists(),
                "readme_exists": readme_path.exists(),
            }
            log_workflow_summary(
                logger,
                event="cli.semantic_onboarding.summary",
                slug=slug,
                artifacts=len(content_mds),
                extra=summary_extra,
            )
        except Exception as exc:
            logger.warning(
                "cli.semantic_onboarding.summary_failed",
                extra={"slug": slug, "error": str(exc)},
            )

        logger.info(
            "cli.semantic_onboarding.completed",
            extra={"slug": slug, "artifacts": int(len(touched)), **summary_extra},
        )
        return 0
    finally:
        if ledger_conn is not None:
            ledger_conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
