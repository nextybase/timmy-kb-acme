# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI helper per il Tag KG Builder (passo intermedio tra Tag Onboarding e Semantic Onboarding)."""
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Optional

from pipeline.cli_runner import run_cli_orchestrator
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_valid_slug, ensure_within_and_resolve
from pipeline.runtime_guard import ensure_strict_runtime
from pipeline.workspace_layout import WorkspaceLayout
from timmy_kb.cli.kg_builder import build_kg_for_workspace
from timmy_kb.versioning import build_env_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Costruisce il Knowledge Graph dei tag (Tag KG Builder)")
    parser.add_argument("slug_pos", nargs="?", help="Slug del cliente (posizionale)")
    parser.add_argument("--slug", type=str, help="Slug del cliente (es. acme-srl)")
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        help="Path esplicito del workspace (es. output/timmy-kb-acme)",
    )
    parser.add_argument(
        "--namespace",
        "-n",
        type=str,
        help="Namespace da passare al Tag KG Builder (default: slug/workspace)",
    )
    parser.add_argument("--run-id", type=str, help="ID di run esplicito per il logging")
    parser.add_argument(
        "--require-env",
        action="store_true",
        help="Richiede variabili d'ambiente per il ClientContext (default: no)",
    )
    return parser.parse_args()


def _resolve_workspace(
    args: argparse.Namespace,
    run_id: str,
) -> tuple[Path, WorkspaceLayout, ClientContext, str]:
    slug_input = args.slug or args.slug_pos

    if args.workspace:
        raw = Path(args.workspace).expanduser().resolve()
        workspace = ensure_within_and_resolve(REPO_ROOT, raw)
        slug = slug_input or Path(workspace).name
        context = ClientContext.load(
            slug=slug,
            require_drive_env=args.require_env,
            run_id=run_id,
            bootstrap_config=False,
            repo_root_dir=workspace,
        )
        layout = WorkspaceLayout.from_context(context)
        workspace = ensure_within_and_resolve(REPO_ROOT, layout.repo_root_dir)
        return workspace, layout, context, layout.slug

    if not slug_input:
        raise ConfigError("Serve uno slug o il path workspace (--workspace).")

    slug = ensure_valid_slug(
        slug_input,
        interactive=False,
        prompt=lambda _: "",
        logger=get_structured_logger("kg_build", run_id=run_id),
    )

    context = ClientContext.load(
        slug=slug,
        require_drive_env=args.require_env,
        run_id=run_id,
        bootstrap_config=False,
    )

    layout = WorkspaceLayout.from_context(context)
    workspace = layout.repo_root_dir
    workspace = ensure_within_and_resolve(REPO_ROOT, workspace)
    return workspace, layout, context, layout.slug


def kg_build_main(
    workspace: Path,
    layout: WorkspaceLayout,
    namespace: Optional[str],
    slug: str,
    run_id: str,
    context: ClientContext,
) -> None:
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = layout.log_file
    logger = get_structured_logger("kg_build", log_file=log_file, context=context, run_id=run_id)
    logger.info(
        "cli.kg_build.started",
        extra={"workspace": str(workspace), "namespace": namespace, "env_fingerprint": build_env_fingerprint()},
    )

    try:
        with phase_scope(logger, stage="tag_kg.build", customer=slug):
            build_kg_for_workspace(context, namespace=namespace)
        logger.info("cli.kg_build.completed", extra={"workspace": str(workspace)})
    except Exception as exc:  # noqa: BLE001
        logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        raise


def main(args: argparse.Namespace) -> None:
    ensure_strict_runtime(context="cli.kg_build")
    run_id = args.run_id or uuid.uuid4().hex
    early_logger = get_structured_logger("kg_build", run_id=run_id)

    try:
        workspace, layout, context, slug = _resolve_workspace(args, run_id)
    except ConfigError as exc:
        early_logger.error("cli.kg_build.invalid_input", extra={"error": str(exc)})
        raise

    try:
        kg_build_main(workspace, layout, args.namespace, slug, run_id, context)
    except KeyboardInterrupt:
        early_logger.error("cli.kg_build.interrupted", extra={"slug": slug, "run_id": run_id})
        raise
    except ConfigError as exc:
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        raise
    except PipelineError as exc:
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        raise
    except Exception as exc:  # noqa: BLE001
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        raise PipelineError(str(exc)) from exc


if __name__ == "__main__":
    run_cli_orchestrator("kg_build", _parse_args, main)
