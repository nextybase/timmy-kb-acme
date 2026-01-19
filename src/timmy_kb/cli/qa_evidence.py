#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

from __future__ import annotations

import argparse
import uuid

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger
from pipeline.observability_config import get_observability_settings
from pipeline.paths import get_repo_root
from pipeline.proc_utils import CmdError, run_cmd
from pipeline.qa_evidence import write_qa_evidence
from pipeline.workspace_layout import WorkspaceLayout, workspace_validation_policy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate structured QA evidence for a slug.")
    parser.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    parser.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return parser.parse_args()


def main() -> int:
    repo_root = str(get_repo_root())
    args = _parse_args()
    slug = args.slug
    run_id = uuid.uuid4().hex
    settings = get_observability_settings()
    logger = get_structured_logger(
        "cli.qa_evidence",
        run_id=run_id,
        level=settings.log_level,
        redact_logs=settings.redact_logs,
        enable_tracing=settings.tracing_enabled,
    )

    ctx = ClientContext.load(slug=slug, require_env=False, run_id=run_id, bootstrap_config=False)
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(ctx)

    checks = [
        ("pre-commit run --all-files", ["pre-commit", "run", "--all-files"]),
        ("pytest -q", ["pytest", "-q"]),
    ]
    checks_executed: list[str] = []
    try:
        for label, cmd in checks:
            checks_executed.append(label)
            run_cmd(cmd, cwd=repo_root, logger=logger, op=label)
        write_qa_evidence(layout.log_dir, checks_executed=checks_executed, qa_status="pass", logger=logger)
        logger.info("cli.qa_evidence.completed", extra={"slug": slug, "checks": checks_executed})
        return 0
    except CmdError as exc:
        write_qa_evidence(layout.log_dir, checks_executed=checks_executed, qa_status="fail", logger=logger)
        err = PipelineError("QA check failed while generating evidence.", code="qa_evidence_failed")
        logger.error("cli.qa_evidence.failed", extra={"slug": slug, "error": str(err), "op": exc.op})
        return int(exit_code_for(err))
    except (ConfigError, PipelineError) as exc:
        logger.error("cli.qa_evidence.failed", extra={"slug": slug, "error": str(exc)})
        return int(exit_code_for(exc))
    except Exception as exc:
        logger.exception("cli.qa_evidence.unexpected_error", extra={"slug": slug, "error": str(exc)})
        return 99


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
