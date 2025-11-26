# SPDX-License-Identifier: GPL-3.0-only
"""CLI helper per il Tag KG Builder (passo intermedio tra Tag Onboarding e Semantic Onboarding)."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Optional

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME, OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.path_utils import ensure_valid_slug, ensure_within_and_resolve
from timmykb.kg_builder import build_kg_for_workspace

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


def _resolve_workspace(args: argparse.Namespace, run_id: str) -> tuple[Path, Optional[ClientContext], str]:
    slug_input = args.slug or args.slug_pos
    context: Optional[ClientContext] = None

    if args.workspace:
        raw = Path(args.workspace).expanduser().resolve()
        workspace = ensure_within_and_resolve(REPO_ROOT, raw)
        slug = slug_input or Path(workspace).name
        return workspace, context, slug

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
        interactive=False,
        require_env=args.require_env,
        run_id=run_id,
    )

    base_attr = getattr(context, "base_dir", None)
    if base_attr is not None:
        workspace = Path(base_attr).resolve()
    else:
        workspace = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    workspace = workspace.resolve()
    workspace = ensure_within_and_resolve(REPO_ROOT, workspace)
    return workspace, context, slug


def _ensure_log_file(base_workspace: Path) -> Path:
    log_dir = ensure_within_and_resolve(base_workspace, base_workspace / LOGS_DIR_NAME)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = ensure_within_and_resolve(log_dir, log_dir / LOG_FILE_NAME)
    return log_file


def kg_build_main(
    workspace: Path, namespace: Optional[str], slug: str, run_id: str, context: Optional[ClientContext]
) -> None:
    log_file = _ensure_log_file(workspace)
    logger = get_structured_logger("kg_build", log_file=log_file, context=context, run_id=run_id)
    logger.info("cli.kg_build.started", extra={"workspace": str(workspace), "namespace": namespace})

    try:
        with phase_scope(logger, stage="tag_kg.build", customer=slug):
            build_kg_for_workspace(workspace, namespace=namespace)
        logger.info("cli.kg_build.completed", extra={"workspace": str(workspace)})
    except Exception as exc:  # noqa: BLE001
        logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        raise


def main() -> None:
    args = _parse_args()
    run_id = args.run_id or uuid.uuid4().hex
    early_logger = get_structured_logger("kg_build", run_id=run_id)

    try:
        workspace, context, slug = _resolve_workspace(args, run_id)
    except ConfigError as exc:
        early_logger.error("cli.kg_build.invalid_input", extra={"error": str(exc)})
        sys.exit(exit_code_for(exc))

    try:
        kg_build_main(workspace, args.namespace, slug, run_id, context)
    except KeyboardInterrupt:
        early_logger.error("cli.kg_build.interrupted")
        sys.exit(130)
    except ConfigError as exc:
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        sys.exit(exit_code_for(exc))
    except PipelineError as exc:
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        sys.exit(exit_code_for(exc))
    except Exception as exc:  # noqa: BLE001
        early_logger.error("cli.kg_build.failed", extra={"error": str(exc)})
        sys.exit(exit_code_for(PipelineError(str(exc))))


if __name__ == "__main__":
    main()
