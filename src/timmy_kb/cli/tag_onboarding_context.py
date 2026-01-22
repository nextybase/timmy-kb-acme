# SPDX-License-Identifier: GPL-3.0-only
"""Utility di setup contesto per l'orchestratore tag_onboarding."""
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout


@dataclass(frozen=True)
class ContextResources:
    """Raccoglie gli artefatti principali necessari all'orchestratore."""

    context: ClientContext
    repo_root_dir: Path
    raw_dir: Path
    semantic_dir: Path
    logger: logging.Logger
    log_file: Path


def prepare_context(
    slug: str,
    *,
    non_interactive: bool,
    run_id: Optional[str],
    require_env: bool,
) -> ContextResources:
    """Carica il contesto cliente e restituisce percorsi/log pronti all'uso."""
    context = ClientContext.load(
        slug=slug,
        require_env=require_env,
        run_id=run_id,
        bootstrap_config=False,
    )

    layout = WorkspaceLayout.from_context(context)
    repo_root_dir = layout.repo_root_dir
    raw_dir = layout.raw_dir
    semantic_dir = layout.semantic_dir
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = layout.log_file

    logger = get_structured_logger("tag_onboarding", log_file=log_file, context=context, run_id=run_id)

    return ContextResources(
        context=context,
        repo_root_dir=repo_root_dir,
        raw_dir=raw_dir,
        semantic_dir=semantic_dir,
        logger=logger,
        log_file=log_file,
    )


__all__ = ["ContextResources", "prepare_context"]
