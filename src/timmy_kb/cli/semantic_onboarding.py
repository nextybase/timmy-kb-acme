#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only

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
    ctx: SemanticContextProtocol = ClientContext.load(slug=slug, require_env=False, run_id=run_id)
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(ctx)
    ledger_conn = None
    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(
        ledger_conn,
        run_id=run_id,
        slug=slug,
        started_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    evidence_json = json.dumps(
        {
            "slug": layout.slug,
            "workspace_root": str(layout.base_dir),
            "config_path": str(layout.config_path),
            "semantic_dir": str(layout.semantic_dir),
        },
        sort_keys=True,
        separators=(",", ":"),
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
                base_dir, _mds, touched = run_semantic_pipeline(
                    ctx,
                    logger,
                    slug=slug,
                )

                # 3) Costruisci il Knowledge Graph dei tag (Tag KG Builder)
                semantic_dir = layout.semantic_dir
                # Path-safety: blocca traversal/symlink fuori semantic_dir.
                tags_raw_path = ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.json")
                if tags_raw_path.exists():
                    with phase_scope(logger, stage="cli.tag_kg_builder", customer=slug):
                        build_kg_for_workspace(base_dir, namespace=slug)
                else:
                    logger.info(
                        "cli.tag_kg_builder.skipped",
                        extra={"slug": slug, "reason": "semantic/tags_raw.json assente"},
                    )
            except (ConfigError, PipelineError) as exc:
                # Mappa verso exit code deterministici (no traceback non gestiti)
                try:
                    decision_ledger.record_decision(
                        ledger_conn,
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state="TAGS_READY",
                        to_state="SEMANTIC_READY",
                        verdict=decision_ledger.DECISION_DENY,
                        subject="semantic_onboarding",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        evidence_json=evidence_json,
                        rationale=str(exc).splitlines()[:1][0] if str(exc) else "error",
                    )
                except Exception as ledger_exc:
                    logger.exception(
                        "cli.semantic_onboarding.ledger_deny_failed",
                        extra={
                            "slug": slug,
                            "run_id": run_id,
                            "stage": "semantic_onboarding",
                            "error": str(ledger_exc).splitlines()[:1][0] if str(ledger_exc) else "error",
                        },
                    )
                logger.error("cli.semantic_onboarding.failed", extra={"slug": slug, "error": str(exc)})
                code: int = int(exit_code_for(exc))  # exit_code_for non è tipizzato: forza int per mypy
                return code
            except Exception as exc:
                try:
                    decision_ledger.record_decision(
                        ledger_conn,
                        decision_id=uuid.uuid4().hex,
                        run_id=run_id,
                        slug=slug,
                        gate_name="semantic_onboarding",
                        from_state="TAGS_READY",
                        to_state="SEMANTIC_READY",
                        verdict=decision_ledger.DECISION_DENY,
                        subject="semantic_onboarding",
                        decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        evidence_json=evidence_json,
                        rationale=str(exc).splitlines()[:1][0] if str(exc) else "error",
                    )
                except Exception as ledger_exc:
                    logger.exception(
                        "cli.semantic_onboarding.ledger_deny_failed",
                        extra={
                            "slug": slug,
                            "run_id": run_id,
                            "stage": "semantic_onboarding",
                            "error": str(ledger_exc).splitlines()[:1][0] if str(ledger_exc) else "error",
                        },
                    )
                logger.exception("cli.semantic_onboarding.unexpected_error", extra={"slug": slug, "error": str(exc)})
                return 99

        decision_ledger.record_decision(
            ledger_conn,
            decision_id=uuid.uuid4().hex,
            run_id=run_id,
            slug=slug,
            gate_name="semantic_onboarding",
            from_state="TAGS_READY",
            to_state="SEMANTIC_READY",
            verdict=decision_ledger.DECISION_ALLOW,
            subject="semantic_onboarding",
            decided_at=_dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            evidence_json=evidence_json,
            rationale="ok",
        )

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
